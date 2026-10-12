/**
 * WebRTC Mesh Manager for real-time bilateral video & audio calling.
 * Connects participants directly using STUN servers and WebSocket signaling.
 */

const RTC_CONFIG: RTCConfiguration = {
  iceServers: [
    { urls: 'stun:stun.l.google.com:19302' },
    { urls: 'stun:stun1.l.google.com:19302' },
    { urls: 'stun:stun2.l.google.com:19302' },
    { urls: 'stun:stun3.l.google.com:19302' },
    { urls: 'stun:stun4.l.google.com:19302' },
    { urls: 'stun:stun.cloudflare.com:3478' },
  ],
  iceCandidatePoolSize: 10,
};

export type SignalMessage =
  | { type: 'offer'; sdp: RTCSessionDescriptionInit }
  | { type: 'answer'; sdp: RTCSessionDescriptionInit }
  | { type: 'ice-candidate'; candidate: RTCIceCandidateInit };

export interface WebRTCManagerOptions {
  localParticipantId: string;
  onRemoteStream: (participantId: string, stream: MediaStream) => void;
  onRemoteStreamRemoved: (participantId: string) => void;
  sendSignal: (targetId: string, signal: SignalMessage) => void;
}

export class WebRTCManager {
  private peers = new Map<string, RTCPeerConnection>();
  private remoteStreams = new Map<string, MediaStream>();
  private pendingCandidates = new Map<string, RTCIceCandidateInit[]>();
  private localVideoTrack: MediaStreamTrack | null = null;
  private localAudioTrack: MediaStreamTrack | null = null;
  private options: WebRTCManagerOptions;

  constructor(options: WebRTCManagerOptions) {
    this.options = options;
  }

  setVideoTrack(track: MediaStreamTrack | null) {
    const wasNull = this.localVideoTrack === null;
    this.localVideoTrack = track;
    this.updateSendersForKind('video', track, wasNull);
  }

  setAudioTrack(track: MediaStreamTrack | null) {
    const wasNull = this.localAudioTrack === null;
    this.localAudioTrack = track;
    this.updateSendersForKind('audio', track, wasNull);
  }

  private updateSendersForKind(
    kind: 'audio' | 'video',
    track: MediaStreamTrack | null,
    wasNull: boolean,
  ) {
    for (const [peerId, pc] of this.peers.entries()) {
      let senderFound = false;
      const senders = pc.getSenders();
      for (const sender of senders) {
        if ((sender as any)._kind === kind || sender.track?.kind === kind) {
          senderFound = true;
          sender.replaceTrack(track).catch((e) => {
            console.warn(`[WebRTC] replaceTrack(${kind}) failed for ${peerId}:`, e);
          });
        }
      }
      if (!senderFound && track) {
        // Add new track and trigger renegotiation
        try {
          const s = pc.addTrack(track, new MediaStream([track]));
          (s as any)._kind = kind;
          // addTrack implicitly schedules a negotiationneeded; force one if
          // state is still stable so the remote learns the new direction
          // even when the queued event collides with an in-flight offer.
          if (pc.signalingState === 'stable') {
            void this.renegotiate(peerId, pc);
          }
        } catch (e) {
          console.warn(`[WebRTC] Failed to add ${kind} track to ${peerId}:`, e);
        }
      } else if (senderFound && track && wasNull) {
        // The transceiver was created with no track (camera/mic was off at
        // offer time). replaceTrack alone updates the sender's track but the
        // remote receiver has no codec info to decode with — we must push a
        // fresh offer so the SDP advertises the actual codec and direction.
        // Wait a beat for replaceTrack to commit before negotiating so the
        // SDP that goes out reflects the real capabilities.
        const offerAfterReplace = () => {
          if (pc.signalingState === 'stable') {
            void this.renegotiate(peerId, pc);
          }
        };
        const sender = senders.find((s) => (s as any)._kind === kind || s.track?.kind === kind);
        if (sender) {
          sender
            .replaceTrack(track)
            .catch((e) => console.warn(`[WebRTC] pre-renegotiate replaceTrack failed:`, e))
            .then(offerAfterReplace);
        } else {
          offerAfterReplace();
        }
      }
    }
  }

  private async renegotiate(remoteId: string, pc: RTCPeerConnection) {
    try {
      if (pc.signalingState !== 'stable') return;
      const offer = await pc.createOffer({
        offerToReceiveAudio: true,
        offerToReceiveVideo: true,
      });
      await pc.setLocalDescription(offer);
      this.options.sendSignal(remoteId, { type: 'offer', sdp: offer });
    } catch (err) {
      console.warn(`[WebRTC] Renegotiation error with ${remoteId}:`, err);
    }
  }

  async initiateCallTo(remoteParticipantId: string) {
    if (remoteParticipantId === this.options.localParticipantId) return;
    let pc = this.peers.get(remoteParticipantId);
    if (!pc) {
      pc = await this.createPeerConnection(remoteParticipantId);
      // createPeerConnection awaits every replaceTrack so the senders
      // already hold their tracks. Send the initial offer explicitly instead
      // of waiting for `onnegotiationneeded` to fire — it can be delayed by
      // other queued microtasks (replaceTrack completion, transceiver init)
      // and racing peers may already have sent us an offer before then,
      // leaving us in `have-remote-offer` where `onnegotiationneeded` skips
      // its work. This explicit call also runs the polite/impolite glare
      // path — both peers initiate simultaneously and the rule in
      // handleSignal sorts it out.
      if (pc.signalingState === 'stable') {
        await this.renegotiate(remoteParticipantId, pc);
      }
      return;
    }

    try {
      if (pc.signalingState === 'stable') {
        await this.renegotiate(remoteParticipantId, pc);
      }
    } catch (err) {
      console.warn(`[WebRTC] Failed to renegotiate ${remoteParticipantId}:`, err);
    }
  }

  async handleSignal(senderId: string, signal: SignalMessage) {
    if (senderId === this.options.localParticipantId) return;

    let pc = this.peers.get(senderId);
    if (!pc) {
      pc = await this.createPeerConnection(senderId);
      // createPeerConnection awaits every replaceTrack so the senders
      // already hold their tracks (or were created empty if the local track
      // is missing). For incoming offers the remote will adapt the answer to
      // whatever direction we advertise here, so waiting guarantees the
      // caller knows the real initial capability set.
    }

    try {
      if (signal.type === 'offer') {
        const isPolite = this.options.localParticipantId < senderId;
        const offerCollision = pc.signalingState !== 'stable';
        if (offerCollision) {
          if (!isPolite) {
            // Impolite peer ignores incoming offer to resolve glare
            return;
          }
          // Polite peer yields: roll back local offer and accept incoming offer
          await pc.setLocalDescription({ type: 'rollback' });
        }

        await pc.setRemoteDescription(new RTCSessionDescription(signal.sdp));

        // Flush any buffered candidates
        const queued = this.pendingCandidates.get(senderId) || [];
        for (const candidate of queued) {
          await pc.addIceCandidate(new RTCIceCandidate(candidate)).catch(() => {});
        }
        this.pendingCandidates.delete(senderId);

        const answer = await pc.createAnswer();
        await pc.setLocalDescription(answer);
        this.options.sendSignal(senderId, {
          type: 'answer',
          sdp: answer,
        });
      } else if (signal.type === 'answer') {
        if (pc.signalingState === 'have-local-offer') {
          await pc.setRemoteDescription(new RTCSessionDescription(signal.sdp));
          const queued = this.pendingCandidates.get(senderId) || [];
          for (const candidate of queued) {
            await pc.addIceCandidate(new RTCIceCandidate(candidate)).catch(() => {});
          }
          this.pendingCandidates.delete(senderId);
        }
      } else if (signal.type === 'ice-candidate') {
        if (signal.candidate) {
          if (pc.remoteDescription && pc.remoteDescription.type) {
            await pc.addIceCandidate(new RTCIceCandidate(signal.candidate)).catch(() => {});
          } else {
            const list = this.pendingCandidates.get(senderId) || [];
            list.push(signal.candidate);
            this.pendingCandidates.set(senderId, list);
          }
        }
      }
    } catch (err) {
      console.warn(`[WebRTC] Error handling signal from ${senderId}:`, err);
    }
  }

  private async createPeerConnection(remoteId: string): Promise<RTCPeerConnection> {
    const pc = new RTCPeerConnection(RTC_CONFIG);
    this.peers.set(remoteId, pc);

    // Track pending track-attachment operations so `onnegotiationneeded`
    // waits until every replaceTrack() in this setup is committed. Otherwise
    // the browser queues a `negotiationneeded` event BEFORE the senders
    // actually hold their tracks, and the first offer that goes out has no
    // codec info — the remote receiver has no way to decode and the tile
    // stays black. Awaiting replaceTrack here plus the pending-set below
    // means the *initial* offer SDP advertises the real codec and direction.
    const pending: Promise<unknown>[] = [];

    // Setup transceivers for audio and video up front (Google Meet pattern)
    try {
      const audioTx = pc.addTransceiver('audio', { direction: 'sendrecv' });
      (audioTx.sender as any)._kind = 'audio';
      if (this.localAudioTrack) {
        pending.push(
          audioTx.sender
            .replaceTrack(this.localAudioTrack)
            .catch((e) => console.warn(`[WebRTC] replaceTrack(audio) failed:`, e)),
        );
      }
    } catch (e) {
      if (this.localAudioTrack) {
        try {
          const s = pc.addTrack(this.localAudioTrack, new MediaStream([this.localAudioTrack]));
          (s as any)._kind = 'audio';
        } catch {
          console.warn(`[WebRTC] addTrack(audio) fallback failed:`, e);
        }
      }
    }

    try {
      const videoTx = pc.addTransceiver('video', { direction: 'sendrecv' });
      (videoTx.sender as any)._kind = 'video';
      if (this.localVideoTrack) {
        pending.push(
          videoTx.sender
            .replaceTrack(this.localVideoTrack)
            .catch((e) => console.warn(`[WebRTC] replaceTrack(video) failed:`, e)),
        );
      }
    } catch (e) {
      if (this.localVideoTrack) {
        try {
          const s = pc.addTrack(this.localVideoTrack, new MediaStream([this.localVideoTrack]));
          (s as any)._kind = 'video';
        } catch {
          console.warn(`[WebRTC] addTrack(video) fallback failed:`, e);
        }
      }
    }

    // Wait until every replaceTrack is committed so the first offer advertises
    // the real codec and direction. addTransceiver alone does not establish
    // codec parameters; those come from the track's capabilities, which only
    // get attached to the sender after replaceTrack resolves.
    if (pending.length) {
      try {
        await Promise.all(pending);
      } catch (e) {
        console.warn(`[WebRTC] track-attach wait failed for ${remoteId}:`, e);
      }
    }

    pc.onicecandidate = (e) => {
      if (e.candidate) {
        this.options.sendSignal(remoteId, {
          type: 'ice-candidate',
          candidate: e.candidate.toJSON(),
        });
      }
    };

    // When the local sender stack changes (initial track attach, replaceTrack
    // when toggling camera, mic-permission changes) the browser fires
    // `negotiationneeded`. If we ignore it, the remote side never learns about
    // the new m-line and the corresponding `RTCRtpReceiver` never gets a track
    // — which is exactly why the guest's tile stays black after the host
    // toggles their camera on mid-call. Always renegotiate and use the
    // polite/impolite glare rule from `handleSignal` so concurrent offers
    // from both peers don't deadlock.
    pc.onnegotiationneeded = async () => {
      try {
        if (pc.signalingState !== 'stable') return;
        const offer = await pc.createOffer({
          offerToReceiveAudio: true,
          offerToReceiveVideo: true,
        });
        await pc.setLocalDescription(offer);
        this.options.sendSignal(remoteId, { type: 'offer', sdp: offer });
        console.info(`[WebRTC] negotiationneeded → sent offer to ${remoteId}`);
        // If the peer races us with their own offer, the polite/impolite
        // glare rule in handleSignal will roll back and accept theirs.
      } catch (err) {
        console.warn(`[WebRTC] negotiationneeded failed for ${remoteId}:`, err);
      }
    };

    pc.ontrack = (e) => {
      // P2P carries video only; live audio runs through the realtime
      // translation pipeline (original relay + TTS) over the meeting socket.
      if (e.track.kind === "audio") return;
      let stream = this.remoteStreams.get(remoteId);
      if (!stream) {
        // addTransceiver-created transceivers do not produce a stream on
        // the track event (`e.streams[0]` is often undefined); use the
        // supplied one when it has tracks, otherwise create our own.
        const incoming = e.streams && e.streams[0];
        stream =
          incoming && incoming.getTracks().length > 0
            ? incoming
            : new MediaStream();
        this.remoteStreams.set(remoteId, stream);
      }
      if (!stream.getTracks().some((t) => t.id === e.track.id)) {
        stream.addTrack(e.track);
      }

      e.track.onended = () => {
        stream?.removeTrack(e.track);
        if (stream && stream.getTracks().length === 0) {
          this.remoteStreams.delete(remoteId);
          this.options.onRemoteStreamRemoved(remoteId);
        } else if (stream) {
          this.options.onRemoteStream(remoteId, new MediaStream(stream.getTracks()));
        }
      };

      // Wrap in a fresh MediaStream copy so React state sees a new reference and re-renders VideoTile immediately
      console.info(`[WebRTC] received ${e.track.kind} track from ${remoteId}`);
      this.options.onRemoteStream(remoteId, new MediaStream(stream.getTracks()));
    };

    pc.onconnectionstatechange = () => {
      if (
        pc.connectionState === 'disconnected' ||
        pc.connectionState === 'failed' ||
        pc.connectionState === 'closed'
      ) {
        this.removePeer(remoteId);
      }
    };

    return pc;
  }

  hasPeer(remoteId: string) {
    return this.peers.has(remoteId);
  }

  removePeer(remoteId: string) {
    const pc = this.peers.get(remoteId);
    if (pc) {
      pc.close();
      this.peers.delete(remoteId);
      this.pendingCandidates.delete(remoteId);
      this.remoteStreams.delete(remoteId);
      this.options.onRemoteStreamRemoved(remoteId);
    }
  }

  dispose() {
    for (const [id, pc] of this.peers.entries()) {
      pc.close();
      this.options.onRemoteStreamRemoved(id);
    }
    this.peers.clear();
    this.pendingCandidates.clear();
    this.remoteStreams.clear();
    this.localVideoTrack = null;
    this.localAudioTrack = null;
  }
}

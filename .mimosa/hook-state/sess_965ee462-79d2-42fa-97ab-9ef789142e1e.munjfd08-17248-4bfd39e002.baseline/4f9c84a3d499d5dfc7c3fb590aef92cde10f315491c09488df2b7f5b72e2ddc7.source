/**
 * WebRTC Mesh Manager for real-time bilateral video & audio calling.
 * Connects participants directly using STUN servers and WebSocket signaling.
 */

const RTC_CONFIG: RTCConfiguration = {
  iceServers: [
    { urls: 'stun:stun.l.google.com:19302' },
    { urls: 'stun:stun1.l.google.com:19302' },
    { urls: 'stun:stun2.l.google.com:19302' },
  ],
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
    this.localVideoTrack = track;
    this.updateSendersForKind('video', track);
  }

  setAudioTrack(track: MediaStreamTrack | null) {
    this.localAudioTrack = track;
    this.updateSendersForKind('audio', track);
  }

  private updateSendersForKind(kind: 'audio' | 'video', track: MediaStreamTrack | null) {
    for (const [peerId, pc] of this.peers.entries()) {
      const senders = pc.getSenders();
      const sender = senders.find((s) => (s as any)._kind === kind || s.track?.kind === kind);
      if (sender) {
        void sender.replaceTrack(track);
      } else if (track) {
        // Add new track and trigger renegotiation
        try {
          const s = pc.addTrack(track, new MediaStream([track]));
          (s as any)._kind = kind;
          void this.renegotiate(peerId, pc);
        } catch (e) {
          console.warn(`[WebRTC] Failed to add ${kind} track to ${peerId}:`, e);
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
      pc = this.createPeerConnection(remoteParticipantId);
    }

    try {
      const offer = await pc.createOffer({
        offerToReceiveAudio: true,
        offerToReceiveVideo: true,
      });
      await pc.setLocalDescription(offer);
      this.options.sendSignal(remoteParticipantId, {
        type: 'offer',
        sdp: offer,
      });
    } catch (err) {
      console.warn(`[WebRTC] Failed to create offer to ${remoteParticipantId}:`, err);
    }
  }

  async handleSignal(senderId: string, signal: SignalMessage) {
    if (senderId === this.options.localParticipantId) return;

    let pc = this.peers.get(senderId);
    if (!pc) {
      pc = this.createPeerConnection(senderId);
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

  private createPeerConnection(remoteId: string): RTCPeerConnection {
    const pc = new RTCPeerConnection(RTC_CONFIG);
    this.peers.set(remoteId, pc);

    // Setup transceivers for audio and video up front (Google Meet pattern)
    try {
      const audioTx = pc.addTransceiver('audio', { direction: 'sendrecv' });
      (audioTx.sender as any)._kind = 'audio';
      if (this.localAudioTrack) {
        void audioTx.sender.replaceTrack(this.localAudioTrack);
      }
    } catch {
      if (this.localAudioTrack) {
        const s = pc.addTrack(this.localAudioTrack, new MediaStream([this.localAudioTrack]));
        (s as any)._kind = 'audio';
      }
    }

    try {
      const videoTx = pc.addTransceiver('video', { direction: 'sendrecv' });
      (videoTx.sender as any)._kind = 'video';
      if (this.localVideoTrack) {
        void videoTx.sender.replaceTrack(this.localVideoTrack);
      }
    } catch {
      if (this.localVideoTrack) {
        const s = pc.addTrack(this.localVideoTrack, new MediaStream([this.localVideoTrack]));
        (s as any)._kind = 'video';
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

    pc.ontrack = (e) => {
      let stream = this.remoteStreams.get(remoteId);
      if (!stream) {
        stream = (e.streams && e.streams[0]) ? e.streams[0] : new MediaStream();
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
        }
      };

      this.options.onRemoteStream(remoteId, stream);
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

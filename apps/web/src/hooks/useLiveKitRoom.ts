import { useEffect, useRef, useState } from 'react';
import {
  ConnectionState, Room, RoomEvent, Track,
  type Participant, type ReconnectContext, type ReconnectPolicy,
} from 'livekit-client';
import { api } from '../lib/api';
import type { AudioMode } from '../lib/types';

export type MediaRoomState = 'unavailable' | 'connecting' | 'connected' | 'reconnecting' | 'error';

export interface MediaPeer {
  id: string;
  name: string;
  self: boolean;
  stream: MediaStream | null;
  isScreenShare: boolean;
  cameraOn: boolean;
  screenShareOn: boolean;
  microphoneOn: boolean;
}

interface MediaCredentials {
  url: string;
  token: string;
}

/**
 * LiveKit connection resilience. After a real disconnect (network flap, token
 * expiry, media-server restart) we re-mint a single-use media token and retry
 * with jittered backoff — a bounded number of times, never silently forever.
 */
const RECONNECT_MAX_ATTEMPTS = 3;
const RECONNECT_BASE_DELAY_MS = 1200;
const RECONNECT_MAX_DELAY_MS = 6000;

/**
 * LiveKit's own auto-reconnect used to hold the room in an amber
 * "Reconnecting" limbo for minutes before finally emitting
 * RoomEvent.Disconnected — the hook's honest bounded retry (fresh
 * single-use token per attempt) almost never governed. This policy gives
 * the SDK two quick internal attempts; then it stops retrying, the
 * Disconnected event fires promptly, and OUR bounded loop takes over, so
 * a stuck media room always ends at the honest error state in tens of
 * seconds instead of minutes.
 */
const liveKitTwoAttemptStopPolicy: ReconnectPolicy = {
  nextRetryDelayInMs(context: ReconnectContext): number | null {
    if (context.retryCount >= 2) return null;
    return 1000;
  },
};

function participantMedia(participant: Participant, self: boolean): MediaPeer {
  const screenTrack = participant.getTrackPublication(Track.Source.ScreenShare)?.track;
  const cameraTrack = participant.getTrackPublication(Track.Source.Camera)?.track;
  const videoTrack = screenTrack ?? cameraTrack;
  const audioPublication = participant.getTrackPublication(Track.Source.Microphone);

  return {
    id: participant.identity,
    name: participant.name || participant.identity,
    self,
    stream: videoTrack?.kind === Track.Kind.Video
      ? new MediaStream([videoTrack.mediaStreamTrack])
      : null,
    isScreenShare: !!screenTrack,
    cameraOn: !!cameraTrack,
    screenShareOn: !!screenTrack,
    microphoneOn: !!audioPublication && !audioPublication.isMuted,
  };
}

export function useLiveKitRoom({
  enabled,
  meetingId,
  participantId,
  audioMode,
  sessionKey,
}: {
  enabled: boolean;
  meetingId: string;
  participantId?: string;
  audioMode: AudioMode;
  /** Latest seat session key; the guest's media-token credential. */
  sessionKey?: () => string | null;
}) {
  const roomRef = useRef<Room | null>(null);
  const audioElementsRef = useRef(new Map<string, HTMLMediaElement>());
  const audioModeRef = useRef(audioMode);
  const audioContainerRef = useRef<HTMLDivElement | null>(null);
  const [state, setState] = useState<MediaRoomState>('unavailable');
  const [error, setError] = useState<string | null>(null);
  const [peers, setPeers] = useState<MediaPeer[]>([]);
  /** Bumped by retry(): re-runs the whole connect effect with a fresh credential. */
  const [retryNonce, setRetryNonce] = useState(0);
  /** Speaker unlock needs a user gesture on mobile browsers: separate from the
   * connection state so a pending autoplay never masquerades as a room error. */
  const [audioBlocked, setAudioBlocked] = useState(false);
  /** Tracks this hook published itself (camera follow, below) for symmetric unpublish. */
  const publishedCameraSidRef = useRef<string | null>(null);

  audioModeRef.current = audioMode;

  useEffect(() => {
    if (!enabled || !participantId) {
      setState('unavailable');
      setPeers([]);
      return;
    }

    const activeParticipantId = participantId;
    let cancelled = false;
    let reconnectAttempt = 0;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let connecting = false;
    const room = new Room({
      adaptiveStream: true,
      dynacast: true,
      reconnectPolicy: liveKitTwoAttemptStopPolicy,
    });
    roomRef.current = room;

    const refreshPeers = () => {
      setPeers([
        participantMedia(room.localParticipant, true),
        ...[...room.remoteParticipants.values()].map((participant) =>
          participantMedia(participant, false)),
      ]);
    };

    const onTrackSubscribed = (track: any) => {
      if (track.kind === Track.Kind.Audio) {
        const element = track.attach() as HTMLMediaElement;
        element.autoplay = true;
        element.muted = audioModeRef.current === 'translated';
        audioContainerRef.current?.appendChild(element);
        audioElementsRef.current.set(track.sid, element);
        void element.play().catch(() => setAudioBlocked(true));
      }
      refreshPeers();
    };

    const onTrackUnsubscribed = (track: any) => {
      const element = audioElementsRef.current.get(track.sid);
      if (element) {
        track.detach(element);
        element.remove();
        audioElementsRef.current.delete(track.sid);
      }
      refreshPeers();
    };

    const onConnectionState = (connectionState: ConnectionState) => {
      if (connectionState === ConnectionState.Connected) {
        reconnectAttempt = 0;
        setAudioBlocked(false);
        setState('connected');
      } else if (connectionState === ConnectionState.Reconnecting) {
        setState('reconnecting');
      } else if (connectionState === ConnectionState.Connecting) {
        setState('connecting');
      }
      // Disconnected is handled by RoomEvent.Disconnected (retry or fail).
    };

    room.on(RoomEvent.TrackSubscribed, onTrackSubscribed);
    room.on(RoomEvent.TrackUnsubscribed, onTrackUnsubscribed);
    room.on(RoomEvent.ParticipantConnected, refreshPeers);
    room.on(RoomEvent.ParticipantDisconnected, refreshPeers);
    room.on(RoomEvent.LocalTrackPublished, refreshPeers);
    room.on(RoomEvent.LocalTrackUnpublished, refreshPeers);
    room.on(RoomEvent.TrackMuted, refreshPeers);
    room.on(RoomEvent.TrackUnmuted, refreshPeers);
    room.on(RoomEvent.ConnectionStateChanged, onConnectionState);

    async function connect(): Promise<void> {
      if (connecting || cancelled || leftOnPurposeRef.current) return;
      connecting = true;
      setState((current) => (current === 'connected' ? 'reconnecting' : 'connecting'));
      try {
        // Every attempt mints a fresh single-use token: a media-server outage
        // longer than the token TTL cannot strand us with a stale credential.
        const data = await api<MediaCredentials>(
          `/api/v1/meetings/${meetingId}/media-token?participant_id=${encodeURIComponent(activeParticipantId)}`,
          {
            method: 'POST',
            // Guests own no organization, so the seat's session key is their
            // media-token credential — the same one /join-ticket accepts.
            body: sessionKey?.() ? { session_key: sessionKey?.() } : undefined,
          },
        );
        if (cancelled) return;
        await room.connect(data.url, data.token);
        if (cancelled) {
          room.disconnect();
          return;
        }
        reconnectAttempt = 0;
        setState('connected');
        refreshPeers();
      } catch (cause) {
        if (cancelled) return;
        scheduleReconnect(
          cause instanceof Error ? cause.message : 'Could not connect to the video room');
      } finally {
        connecting = false;
      }
    }

    function scheduleReconnect(reason: string) {
      if (cancelled) return;
      reconnectAttempt += 1;
      if (reconnectAttempt > RECONNECT_MAX_ATTEMPTS) {
        // Honest failure: the video room is DOWN, not "reconnecting".
        setError(reason);
        setState('error');
        return;
      }
      const jitter = Math.random() * RECONNECT_BASE_DELAY_MS;
      const delay = Math.min(
        RECONNECT_BASE_DELAY_MS * Math.pow(2, reconnectAttempt - 1),
        RECONNECT_MAX_DELAY_MS,
      ) + jitter;
      setState('reconnecting');
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        void connect();
      }, delay);
    }

    const onDisconnected = () => {
      if (cancelled) return;
      // A deliberate hang-up (Leave button) must not trigger retries.
      if (leftOnPurposeRef.current) {
        setState('unavailable');
        return;
      }
      // A disconnect is not "reconnecting forever": retry a bounded number of
      // times with fresh credentials, then report an actionable error.
      scheduleReconnect('Video connection lost — tap Reconnect to join the room again.');
    };

    room.on(RoomEvent.Disconnected, onDisconnected);

    void connect();
    return () => {
      cancelled = true;
      if (reconnectTimer !== null) clearTimeout(reconnectTimer);
      reconnectTimer = null;
      room.removeAllListeners();
      room.disconnect();
      if (roomRef.current === room) roomRef.current = null;
      for (const element of audioElementsRef.current.values()) element.remove();
      audioElementsRef.current.clear();
      publishedCameraSidRef.current = null;
      setPeers([]);
      setAudioBlocked(false);
    };
  }, [enabled, meetingId, participantId, retryNonce]);

  useEffect(() => {
    const muted = audioMode === 'translated';
    for (const element of audioElementsRef.current.values()) element.muted = muted;
  }, [audioMode]);

  async function publishMicrophone(track: MediaStreamTrack) {
    const room = roomRef.current;
    if (room?.state === ConnectionState.Connected) {
      await room.localParticipant.publishTrack(track, { source: Track.Source.Microphone });
    }
  }

  async function unpublishMicrophone(track: MediaStreamTrack) {
    const room = roomRef.current;
    if (room?.state === ConnectionState.Connected) {
      await room.localParticipant.unpublishTrack(track);
    }
  }

  /**
   * Publish an already-open camera MediaStreamTrack (hardware or virtual-studio
   * fallback). Used when the camera was enabled in the lobby / before LiveKit
   * finished connecting, `retryPhysicalCamera` granted permission late, or a
   * permission-denied stream needs to reach the room — every path that used to
   * leave the local tile live but the remote tile black.
   */
  async function publishCameraTrack(track: MediaStreamTrack) {
    const room = roomRef.current;
    if (!room || room.state !== ConnectionState.Connected) {
      throw new Error('Video room is not connected');
    }
    if (publishedCameraSidRef.current) {
      return;
    }
    const publication = await room.localParticipant.publishTrack(track, {
      source: Track.Source.Camera,
    });
    publishedCameraSidRef.current = publication?.trackSid ?? null;
    setPeers((current) => current.map((peer) =>
      peer.self ? participantMedia(room.localParticipant, true) : peer));
  }

  async function unpublishCameraTrackIfPublished() {
    const room = roomRef.current;
    const sid = publishedCameraSidRef.current;
    if (!room?.localParticipant || !sid) return;
    publishedCameraSidRef.current = null;
    const publication = room.localParticipant
      .getTrackPublication(Track.Source.Camera);
    try {
      if (publication?.track) {
        await room.localParticipant.unpublishTrack(publication.track);
      }
    } catch {
      // Track may already be gone; the follow-up state refresh below is what matters.
    }
    setPeers((current) => current.map((peer) =>
      peer.self ? participantMedia(room.localParticipant, true) : peer));
  }

  async function setCameraEnabled(nextEnabled: boolean) {
    const room = roomRef.current;
    if (!room || room.state !== ConnectionState.Connected) throw new Error('Video room is not connected');
    await room.localParticipant.setCameraEnabled(nextEnabled);
    publishedCameraSidRef.current = null;
    setPeers((current) => current.map((peer) =>
      peer.self ? participantMedia(room.localParticipant, true) : peer));
  }

  async function setScreenShareEnabled(enabled: boolean) {
    const room = roomRef.current;
    if (!room || room.state !== ConnectionState.Connected) throw new Error('Video room is not connected');
    await room.localParticipant.setScreenShareEnabled(enabled);
  }

  async function unlockAudio() {
    await roomRef.current?.startAudio();
  }

  /** Leave the room on purpose (Leave button / back-to-lobby): stop the
   * reconnect machinery so nobody retries a hang-up. */
  const leftOnPurposeRef = useRef(false);
  async function leave() {
    leftOnPurposeRef.current = true;
    const room = roomRef.current;
    if (room && room.state !== ConnectionState.Disconnected) {
      room.disconnect();
    }
  }

  /** Retry the connection immediately with a fresh credential budget. */
  function retry() {
    leftOnPurposeRef.current = false;
    setRetryNonce((nonce) => nonce + 1);
  }

  return {
    state,
    error,
    peers,
    audioBlocked,
    audioContainerRef,
    retryNonce,
    publishMicrophone,
    unpublishMicrophone,
    publishCameraTrack,
    unpublishCameraTrackIfPublished,
    setCameraEnabled,
    setScreenShareEnabled,
    unlockAudio,
    leave,
    retry,
  };
}

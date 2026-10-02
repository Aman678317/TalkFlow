import { useEffect, useRef, useState } from 'react';
import { ConnectionState, Room, RoomEvent, Track, type Participant } from 'livekit-client';
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
}: {
  enabled: boolean;
  meetingId: string;
  participantId?: string;
  audioMode: AudioMode;
}) {
  const roomRef = useRef<Room | null>(null);
  const audioElementsRef = useRef(new Map<string, HTMLMediaElement>());
  const audioModeRef = useRef(audioMode);
  const audioContainerRef = useRef<HTMLDivElement | null>(null);
  const [state, setState] = useState<MediaRoomState>('unavailable');
  const [error, setError] = useState<string | null>(null);
  const [peers, setPeers] = useState<MediaPeer[]>([]);

  audioModeRef.current = audioMode;

  useEffect(() => {
    if (!enabled || !participantId) {
      setState('unavailable');
      setPeers([]);
      return;
    }

    const activeParticipantId = participantId;
    let cancelled = false;
    const room = new Room({ adaptiveStream: true, dynacast: true });
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
        void element.play().catch(() => setError('Click the call page to enable speaker audio.'));
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
      if (connectionState === ConnectionState.Connected) setState('connected');
      else if (connectionState === ConnectionState.Reconnecting) setState('reconnecting');
      else if (connectionState === ConnectionState.Connecting) setState('connecting');
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
    room.on(RoomEvent.Disconnected, () => {
      if (!cancelled) setState('reconnecting');
    });

    async function connect() {
      setState('connecting');
      setError(null);
      try {
        const data = await api<MediaCredentials>(
          `/api/v1/meetings/${meetingId}/media-token?participant_id=${encodeURIComponent(activeParticipantId)}`,
          { method: 'POST' },
        );
        if (cancelled) return;
        await room.connect(data.url, data.token);
        if (cancelled) {
          room.disconnect();
          return;
        }
        refreshPeers();
      } catch (cause) {
        if (cancelled) return;
        setError(cause instanceof Error ? cause.message : 'Could not connect to the video room');
        setState('error');
      }
    }

    void connect();
    return () => {
      cancelled = true;
      room.removeAllListeners();
      room.disconnect();
      if (roomRef.current === room) roomRef.current = null;
      for (const element of audioElementsRef.current.values()) element.remove();
      audioElementsRef.current.clear();
      setPeers([]);
    };
  }, [enabled, meetingId, participantId]);

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

  async function setCameraEnabled(enabled: boolean) {
    const room = roomRef.current;
    if (!room || room.state !== ConnectionState.Connected) throw new Error('Video room is not connected');
    await room.localParticipant.setCameraEnabled(enabled);
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

  return {
    state,
    error,
    peers,
    audioContainerRef,
    publishMicrophone,
    unpublishMicrophone,
    setCameraEnabled,
    setScreenShareEnabled,
    unlockAudio,
  };
}
// SessionTrackManager - Connects Web Audio streams to Amazon Connect WebRTC PeerConnection
import { LOGGER_PREFIX } from "../constants";

export class SessionTrackManager {
  constructor(audioStreamManager) {
    this.audioStreamManager = audioStreamManager;
    this.currentContact = null;
    this.activePeerConnection = null;
    this.originalSenderTrack = null;
  }

  setContact(contact) {
    this.currentContact = contact;
    console.log(`${LOGGER_PREFIX} - SessionTrackManager registered active contact:`, contact?.getContactId());
  }

  /**
   * Replaces the outbound audio sender track on the active WebRTC PeerConnection
   * with the synthesized translated audio stream destined for the customer.
   */
  async replaceOutgoingTrack() {
    try {
      const mixedStream = this.audioStreamManager.getMediaStream();
      const mixedAudioTrack = mixedStream.getAudioTracks()[0];
      if (!mixedAudioTrack) {
        console.warn(`${LOGGER_PREFIX} - No audio track found on destination stream`);
        return;
      }

      // Access Amazon Connect RTC session if available
      const rtcSession = window.connect?.core?.getSoftphoneManager?.()?.getSession?.();
      const peerConn = rtcSession?.peerConnection || this.activePeerConnection;

      if (!peerConn) {
        console.info(`${LOGGER_PREFIX} - Peer connection not yet active. Track will bind upon call connection.`);
        return;
      }

      const senders = peerConn.getSenders();
      const audioSender = senders.find(s => s.track && s.track.kind === "audio") || senders.find(s => s.track === null);

      if (audioSender) {
        if (!this.originalSenderTrack) {
          this.originalSenderTrack = audioSender.track;
        }
        await audioSender.replaceTrack(mixedAudioTrack);
        console.log(`${LOGGER_PREFIX} - Successfully replaced WebRTC outbound audio sender track with translated audio`);
      } else {
        peerConn.addTrack(mixedAudioTrack, mixedStream);
        console.log(`${LOGGER_PREFIX} - Added new translated audio track to peer connection`);
      }
    } catch (error) {
      console.error(`${LOGGER_PREFIX} - Failed to replace outgoing audio track:`, error);
    }
  }

  /**
   * Restores the default microphone audio track to the WebRTC connection
   */
  async restoreMicrophoneTrack(micStream) {
    try {
      const micTrack = micStream?.getAudioTracks()[0] || this.originalSenderTrack;
      if (!micTrack) return;

      const rtcSession = window.connect?.core?.getSoftphoneManager?.()?.getSession?.();
      const peerConn = rtcSession?.peerConnection || this.activePeerConnection;
      if (!peerConn) return;

      const audioSender = peerConn.getSenders().find(s => s.track);
      if (audioSender) {
        await audioSender.replaceTrack(micTrack);
        console.log(`${LOGGER_PREFIX} - Restored original microphone track to WebRTC connection`);
      }
    } catch (error) {
      console.error(`${LOGGER_PREFIX} - Failed to restore microphone track:`, error);
    }
  }
}

// Audio buffer transformation utilities for streaming transcription
import { Buffer } from "buffer";

export async function* getAWSCustomerStream(audioStream, sampleRate, onStart) {
  if (onStart) onStart(Date.now());
  const reader = audioStream.getReader();
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      yield {
        AudioEvent: {
          AudioChunk: Buffer.from(value),
        },
      };
    }
  } finally {
    reader.releaseLock();
  }
}

export async function* getAWSAgentStream(audioStream, sampleRate, onStart) {
  if (onStart) onStart(Date.now());
  const reader = audioStream.getReader();
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      yield {
        AudioEvent: {
          AudioChunk: Buffer.from(value),
        },
      };
    }
  } finally {
    reader.releaseLock();
  }
}

export function getPartialTranscript(results, lastProcessedIndex) {
  if (!results || results.length === 0) return null;
  const latest = results[0];
  if (latest.IsPartial && latest.Alternatives && latest.Alternatives.length > 0) {
    return { partialTranscript: latest.Alternatives[0].Transcript };
  }
  return null;
}

export function getFinalTranscript(results, lastProcessedIndex, enableStability) {
  if (!results || results.length === 0) return null;
  const latest = results[0];
  if (!latest.IsPartial && latest.Alternatives && latest.Alternatives.length > 0) {
    return {
      finalTranscript: latest.Alternatives[0].Transcript,
      startTime: latest.StartTime,
      endTime: latest.EndTime,
      lastProcessedIndex: lastProcessedIndex + 1
    };
  }
  return null;
}

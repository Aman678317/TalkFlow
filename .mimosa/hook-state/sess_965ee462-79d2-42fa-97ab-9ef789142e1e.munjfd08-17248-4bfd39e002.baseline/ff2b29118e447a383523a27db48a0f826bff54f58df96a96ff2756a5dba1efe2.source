// Transcribe Adapter for AWS speech-to-text fallback
import { StartStreamTranscriptionCommand, TranscribeStreamingClient } from "@aws-sdk/client-transcribe-streaming";
import { TRANSCRIBE_CONFIG } from "../config";
import { LOGGER_PREFIX } from "../constants";
import { getValidAwsCredentials, hasValidAwsCredentials } from "../utils/authUtility";
import { getAWSCustomerStream, getAWSAgentStream, getPartialTranscript, getFinalTranscript } from "../utils/transcribeUtils";

let _transcribeClient = null;

async function getTranscribeClient() {
  if (_transcribeClient && hasValidAwsCredentials()) {
    return _transcribeClient;
  }
  const credentials = await getValidAwsCredentials();
  _transcribeClient = new TranscribeStreamingClient({
    region: TRANSCRIBE_CONFIG.transcribeRegion || "us-east-1",
    credentials: {
      accessKeyId: credentials.accessKeyId,
      secretAccessKey: credentials.secretAccessKey,
      sessionToken: credentials.sessionToken,
    },
  });
  return _transcribeClient;
}

export async function startStreamTranscription(options) {
  const {
    audioStream,
    sampleRate = 16000,
    languageCode = "en-US",
    onFinalTranscribeEvent,
    onPartialTranscribeEvent,
    participant = "agent"
  } = options;

  const client = await getTranscribeClient();
  const streamGenerator = participant === "customer" 
    ? getAWSCustomerStream(audioStream, sampleRate)
    : getAWSAgentStream(audioStream, sampleRate);

  const command = new StartStreamTranscriptionCommand({
    LanguageCode: languageCode,
    MediaEncoding: "pcm",
    MediaSampleRateHertz: sampleRate,
    AudioStream: streamGenerator,
    EnablePartialResultsStabilization: true,
    PartialResultsStability: "medium"
  });

  try {
    const response = await client.send(command);
    let lastProcessedIndex = 0;
    for await (const event of response.TranscriptResultStream) {
      const results = event.TranscriptEvent?.Transcript?.Results;
      const partial = getPartialTranscript(results, lastProcessedIndex);
      if (partial && onPartialTranscribeEvent) {
        onPartialTranscribeEvent(partial.partialTranscript);
      }
      const finalRes = getFinalTranscript(results, lastProcessedIndex, true);
      if (finalRes && onFinalTranscribeEvent) {
        lastProcessedIndex = finalRes.lastProcessedIndex;
        onFinalTranscribeEvent(finalRes.finalTranscript, finalRes.startTime, finalRes.endTime);
      }
    }
  } catch (err) {
    console.error(`${LOGGER_PREFIX} - Transcribe streaming error:`, err);
  }
}

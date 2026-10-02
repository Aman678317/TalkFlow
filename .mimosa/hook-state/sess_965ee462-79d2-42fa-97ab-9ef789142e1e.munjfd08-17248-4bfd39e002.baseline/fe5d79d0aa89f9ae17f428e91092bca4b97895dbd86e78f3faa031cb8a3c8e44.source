// Polly Adapter for AWS Polly speech synthesis fallback
import { PollyClient, SynthesizeSpeechCommand } from "@aws-sdk/client-polly";
import { POLLY_CONFIG } from "../config";
import { LOGGER_PREFIX } from "../constants";
import { getValidAwsCredentials, hasValidAwsCredentials } from "../utils/authUtility";
import { Buffer } from "buffer";

let _pollyClient = null;

async function getPollyClient() {
  if (_pollyClient && hasValidAwsCredentials()) {
    return _pollyClient;
  }
  const credentials = await getValidAwsCredentials();
  _pollyClient = new PollyClient({
    region: POLLY_CONFIG.pollyRegion || "us-east-1",
    credentials: {
      accessKeyId: credentials.accessKeyId,
      secretAccessKey: credentials.secretAccessKey,
      sessionToken: credentials.sessionToken,
    },
  });
  return _pollyClient;
}

export async function synthesizeSpeechAWS(text, languageCode = "en-US", voiceId = "Joanna") {
  const client = await getPollyClient();
  const command = new SynthesizeSpeechCommand({
    OutputFormat: "pcm",
    SampleRate: "16000",
    Text: text,
    VoiceId: voiceId,
    Engine: "neural"
  });

  try {
    const response = await client.send(command);
    const audioBytes = await response.AudioStream.transformToByteArray();
    return audioBytes.buffer;
  } catch (err) {
    console.error(`${LOGGER_PREFIX} - AWS Polly error:`, err);
    return null;
  }
}

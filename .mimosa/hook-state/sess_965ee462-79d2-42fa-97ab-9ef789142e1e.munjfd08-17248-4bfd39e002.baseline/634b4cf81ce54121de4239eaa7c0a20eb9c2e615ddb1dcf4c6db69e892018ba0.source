// Translate Adapter for AWS Translate fallback
import { TranslateClient, TranslateTextCommand } from "@aws-sdk/client-translate";
import { TRANSLATE_CONFIG } from "../config";
import { LOGGER_PREFIX } from "../constants";
import { getValidAwsCredentials, hasValidAwsCredentials } from "../utils/authUtility";

let _translateClient = null;

async function getTranslateClient() {
  if (_translateClient && hasValidAwsCredentials()) {
    return _translateClient;
  }
  const credentials = await getValidAwsCredentials();
  _translateClient = new TranslateClient({
    region: TRANSLATE_CONFIG.translateRegion || "us-east-1",
    credentials: {
      accessKeyId: credentials.accessKeyId,
      secretAccessKey: credentials.secretAccessKey,
      sessionToken: credentials.sessionToken,
    },
  });
  return _translateClient;
}

export async function translateTextAWS(text, sourceLang, targetLang) {
  const client = await getTranslateClient();
  const command = new TranslateTextCommand({
    Text: text,
    SourceLanguageCode: sourceLang || "auto",
    TargetLanguageCode: targetLang || "en"
  });

  try {
    const response = await client.send(command);
    return response.TranslatedText;
  } catch (err) {
    console.error(`${LOGGER_PREFIX} - AWS Translate error:`, err);
    return text;
  }
}

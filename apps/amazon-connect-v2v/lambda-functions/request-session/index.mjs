// Desi Voice-to-Voice Realtime Session Proxy Lambda
// Connects to Desi Language AI / GlobalTalk AI Gateway (/v3/voice/realtime)
export const handler = async (event) => {
  const desiProdApiKey = process.env.DESI_API_KEY || process.env.GTK_API_KEY;
  const desiDevApiKey = process.env.DESI_DEV_API_KEY || desiProdApiKey;

  let body;
  if (typeof event.body === 'string') {
    try {
      body = JSON.parse(event.body);
    } catch {
      body = {};
    }
  } else {
    body = event.body || {};
  }

  // Determine environment: 'prod' or 'dev'
  const environment = body?.environment || 'prod';
  if (environment !== 'dev' && environment !== 'prod') {
    return {
      statusCode: 400,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        error: 'Invalid environment parameter. Must be "dev" or "prod".'
      })
    };
  }

  // Base URL selection
  const defaultBaseUrl = environment === 'dev'
    ? (process.env.DESI_DEV_API_URL || 'http://127.0.0.1:8088')
    : (process.env.DESI_API_URL || 'https://api.globaltalk.ai');

  const apiKey = environment === 'dev' ? desiDevApiKey : desiProdApiKey;

  if (!apiKey) {
    return {
      statusCode: 500,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        error: `Missing API key for ${environment} environment. Please set DESI_API_KEY or DESI_DEV_API_KEY.`
      })
    };
  }

  try {
    const reqPayload = {
      source_media_content_type: body.source_media_content_type || 'audio/pcm;encoding=s16le;rate=16000',
      target_media_content_type: body.target_media_content_type || 'audio/pcm;encoding=s16le;rate=16000',
      source_language: body.source_language || 'en',
      source_language_mode: body.source_language_mode || 'fixed',
      target_languages: body.target_languages || ['hi'],
      target_media_languages: body.target_media_languages || body.target_languages || ['hi'],
      target_media_voice: body.target_media_voice || 'female',
      formality: body.formality || 'formal',
      respectful_suffix: body.respectful_suffix ?? true,
      domain: body.domain || 'general',
      meeting_id: body.meeting_id || `connect_${Date.now()}`
    };

    console.log(`[DESI V2V ${environment.toUpperCase()}] Requesting realtime voice session at ${defaultBaseUrl}/v3/voice/realtime`);

    const response = await fetch(`${defaultBaseUrl}/v3/voice/realtime`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${apiKey}`,
        'X-Desi-Key': apiKey,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(reqPayload)
    });

    const rawResponseBody = await response.text();
    let data;
    try {
      data = JSON.parse(rawResponseBody);
    } catch {
      data = { raw: rawResponseBody };
    }

    if (!response.ok) {
      console.error(`Desi V2V error: ${response.status}`, data);
      return {
        statusCode: response.status,
        headers: {
          'Content-Type': 'application/json',
          'Access-Control-Allow-Origin': '*'
        },
        body: JSON.stringify({
          error: `Desi API error: ${response.status}`,
          details: data
        })
      };
    }

    return {
      statusCode: 200,
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*'
      },
      body: JSON.stringify(data)
    };
  } catch (error) {
    console.error('Request session handler failure:', error);
    return {
      statusCode: 500,
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*'
      },
      body: JSON.stringify({ error: error.message })
    };
  }
};

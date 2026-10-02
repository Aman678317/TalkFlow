// Desi Language Catalog Proxy Lambda
// Discovers supported world languages and 22 Eighth Schedule Indian languages
export const handler = async (event) => {
  const desiApiKey = process.env.DESI_API_KEY || process.env.GTK_API_KEY;
  const baseUrl = process.env.DESI_API_URL || 'https://api.globaltalk.ai';

  let body = {};
  if (typeof event.body === 'string') {
    try {
      body = JSON.parse(event.body);
    } catch {
      body = {};
    }
  } else if (event.body) {
    body = event.body;
  }

  const type = body.type || event.queryStringParameters?.type || 'source';

  try {
    const headers = {
      'Authorization': `Bearer ${desiApiKey}`,
      'X-Desi-Key': desiApiKey || '',
      'Content-Type': 'application/json'
    };

    // Fetch standard languages and Indic catalog in parallel
    const [stdRes, indicRes] = await Promise.all([
      fetch(`${baseUrl}/v2/languages?type=${type}`, { method: 'GET', headers }).catch(() => null),
      fetch(`${baseUrl}/v2/desi/languages`, { method: 'GET', headers }).catch(() => null)
    ]);

    let languages = [];
    if (stdRes && stdRes.ok) {
      languages = await stdRes.json();
    }

    let indicLanguages = [];
    if (indicRes && indicRes.ok) {
      const data = await indicRes.json();
      indicLanguages = (data.languages || []).map(l => ({
        language: l.code,
        name: `${l.name} (${l.native_name})`,
        supports_formality: true,
        script: l.script,
        honorific_tiers: l.honorific_tiers
      }));
    }

    // Merge without duplicate language codes
    const seen = new Set(languages.map(l => l.language.toLowerCase()));
    for (const ind of indicLanguages) {
      if (!seen.has(ind.language.toLowerCase())) {
        languages.push(ind);
        seen.add(ind.language.toLowerCase());
      }
    }

    return {
      statusCode: 200,
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*'
      },
      body: JSON.stringify(languages)
    };
  } catch (error) {
    console.error('Get languages handler error:', error);
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

import { useState } from 'react';
import { Card, Button, Badge } from '../components/ui';
import { BookOpen, ExternalLink } from 'lucide-react';

type SdkTab = 'cli' | 'python' | 'typescript' | 'java' | 'dotnet' | 'curl';

export default function DocsPage() {
  const [activeTab, setActiveTab] = useState<SdkTab>('cli');
  const [copied, setCopied] = useState(false);

  const snippets: Record<SdkTab, { title: string; install: string; code: string }> = {
    cli: {
      title: 'Desi & GlobalTalk CLI',
      install: 'npm install -g @globaltalk-ai/desi-cli',
      code: `# Set API Key
export DESI_API_KEY="gtk_your_api_key"

# Translate with Indic Honorifics (-ji / Aap)
desi translate "Hello friend, welcome" --to hi --honorific formal --respectful-suffix

# Transliterate Hinglish to Devanagari
desi transliterate "Dhanyavaad dost" --to devanagari

# Polish text style
desi write "we gotta ship this feature" --style business --tone diplomatic`,
    },
    python: {
      title: 'Python SDK (desi-python)',
      install: 'pip install -e sdk/python/desi-python',
      code: `from desi import DesiClient, IndicHonorific

client = DesiClient(auth_key="gtk_your_api_key")

# Standard text translation
res = client.translate_text("Welcome to our office!", target_lang="DE")
print(res.text)

# Indic translation with Aap/Tum/Tu honorifics
indic = client.translate_desi(
    "Hello friend, welcome to our office.",
    target_lang="hi",
    honorific=IndicHonorific.FORMAL,
    respectful_suffix=True
)
print(indic.text)  # "नमस्ते दोस्त, हमारे कार्यालय में आपका स्वागत है जी।"`,
    },
    typescript: {
      title: 'TypeScript / Node.js SDK (@globaltalk/sdk)',
      install: 'npm install @globaltalk/sdk',
      code: `import { DesiClient, FormalityTier, IndicScript } from '@globaltalk/sdk';

const client = new DesiClient({ apiKey: 'gtk_your_api_key' });

// Indic Translation with cultural honorifics
const res = await client.translateDesi({
  text: 'Hello friend, welcome to our office.',
  targetLang: 'hi',
  honorific: FormalityTier.FORMAL,
  respectfulSuffix: true,
});
console.log(res.translations[0].text);

// Script Transliteration
const translit = await client.transliterate({
  text: 'Dhanyavaad dost',
  targetScript: IndicScript.DEVANAGARI,
});
console.log(translit.results[0].transliteratedText);`,
    },
    java: {
      title: 'Java SDK (com.desi.api:desi-java)',
      install: `<!-- Maven pom.xml -->
<dependency>
    <groupId>com.desi.api</groupId>
    <artifactId>desi-java</artifactId>
    <version>1.0.0</version>
</dependency>`,
      code: `import com.desi.api.DesiClient;
import com.desi.api.DesiHonorific;
import com.desi.api.LanguageCode;
import com.desi.api.model.DesiTextResult;
import com.desi.api.model.DesiTranslateOptions;

DesiClient client = new DesiClient("gtk_your_api_key");
DesiTranslateOptions opts = new DesiTranslateOptions()
        .setHonorific(DesiHonorific.FORMAL)
        .setRespectfulSuffix(true);

DesiTextResult res = client.translateDesi("Hello friend, welcome", LanguageCode.HINDI, opts);
System.out.println(res.getText());`,
    },
    dotnet: {
      title: '.NET SDK (Desi.Client)',
      install: 'dotnet add package Desi.Client',
      code: `using System;
using GlobalTalk.Desi;

var client = new DesiClient("gtk_your_api_key");
var res = await client.TranslateTextAsync(
    "Hello friend, welcome to our office.",
    targetLanguageCode: "hi"
);
Console.WriteLine(res.Text);`,
    },
    curl: {
      title: 'REST API (cURL)',
      install: '# Standard HTTP REST API',
      code: `curl -X POST "http://127.0.0.1:8088/v2/desi/translate" \\
  -H "X-API-Key: gtk_your_api_key" \\
  -H "Content-Type: application/json" \\
  -d '{
    "text": "Hello friend, welcome to our office.",
    "target_lang": "hi",
    "honorific": "formal",
    "respectful_suffix": true
  }'`,
    },
  };

  const copyCode = async () => {
    await navigator.clipboard.writeText(`${snippets[activeTab].install}\n\n${snippets[activeTab].code}`);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-4 lg:p-8">
      {/* Header */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-ink-900">Developer Documentation & SDKs</h1>
            <Badge tone="good">v2.1 API</Badge>
          </div>
          <p className="mt-1 text-sm text-ink-500">
            Official client SDKs, command-line interface, and REST API reference for GlobalTalk AI.
          </p>
        </div>
        <div className="flex gap-2">
          <a href="/api/docs" target="_blank" rel="noreferrer">
            <Button variant="secondary" size="sm">
              <ExternalLink className="mr-1.5 h-3.5 w-3.5" /> Swagger UI
            </Button>
          </a>
          <a href="/api/openapi.json" target="_blank" rel="noreferrer">
            <Button variant="secondary" size="sm">
              <BookOpen className="mr-1.5 h-3.5 w-3.5" /> OpenAPI Schema
            </Button>
          </a>
        </div>
      </div>

      {/* Interactive SDK Selector */}
      <Card title="Client Libraries & Quickstart">
        <div className="mb-4 flex flex-wrap gap-2 border-b border-ink-100 pb-3">
          {(['cli', 'python', 'typescript', 'java', 'dotnet', 'curl'] as SdkTab[]).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                activeTab === tab
                  ? 'bg-iris-600 text-white shadow-sm'
                  : 'bg-ink-100 text-ink-600 hover:bg-ink-200'
              }`}
            >
              {tab.toUpperCase()}
            </button>
          ))}
        </div>

        <div className="space-y-3">
          <div>
            <div className="flex items-center justify-between pb-1">
              <span className="text-xs font-semibold uppercase tracking-wider text-ink-400">Installation</span>
              <button onClick={copyCode} className="text-xs font-medium text-iris-600 hover:underline">
                {copied ? '✓ Copied' : 'Copy snippet'}
              </button>
            </div>
            <pre className="overflow-x-auto rounded-lg bg-ink-950 p-3 font-mono text-xs text-signal-300">
              {snippets[activeTab].install}
            </pre>
          </div>

          <div>
            <span className="text-xs font-semibold uppercase tracking-wider text-ink-400">Usage Example</span>
            <pre className="mt-1 overflow-x-auto rounded-lg bg-ink-950 p-4 font-mono text-xs leading-relaxed text-signal-200">
              {snippets[activeTab].code}
            </pre>
          </div>
        </div>
      </Card>

      {/* Architecture & Core Principles */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card title="Canonical Source Invariant">
          <p className="text-xs leading-relaxed text-ink-600">
            Human speech or text is the only immutable semantic source of truth. Translation fan-out to listeners
            occurs independently without intermediate translation chains or recursive AI compounding.
          </p>
        </Card>

        <Card title="22 Indic Languages">
          <p className="text-xs leading-relaxed text-ink-600">
            Native support for all Eighth Schedule languages recognized by the Constitution of India, complete with
            cultural formality honorifics (<em>Aap / Tum / Tu</em>) and phonetic transliteration.
          </p>
        </Card>

        <Card title="Zero Vendor Lock-in">
          <p className="text-xs leading-relaxed text-ink-600">
            Drop-in compatible with standard Desi wire protocols and OpenAPI 3.1. All SDKs released under the MIT
            License with connection pooling and resilient jitter backoff.
          </p>
        </Card>
      </div>
    </div>
  );
}

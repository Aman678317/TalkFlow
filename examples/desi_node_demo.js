/**
 * GlobalTalk AI — Official desi-node (v1.28.0) Client Conformance Demo.
 *
 * Demonstrates standard Node.js client integration with GlobalTalk AI:
 * - Text translation (/v2/translate) with single text & bulk array
 * - HTML website tag-handling (/v2/translate with tag_handling=html)
 * - Desi Write rephrasing (/v2/write/rephrase with writing_style & tone)
 * - Account usage metrics (/v2/usage)
 * - Supported language discovery (/v2/languages)
 * - Multilingual glossaries (/v3/glossaries)
 * - Style rules (/v3/style_rules)
 * - Translation memories (/v3/translation_memories)
 *
 * Usage:
 *   node examples/desi_node_demo.js
 */

const SERVER_URL = process.env.GLOBAL_TALK_URL || 'http://127.0.0.1:8088';
const AUTH_KEY = process.env.DESI_AUTH_KEY || process.env.DEEPL_AUTH_KEY || 'gtk_demo_key:fx';

const HEADERS = {
    'Authorization': `Desi-Auth-Key ${AUTH_KEY}`,
    'Content-Type': 'application/json',
};

async function apiRequest(path, method = 'GET', body = null) {
    const url = `${SERVER_URL}${path}`;
    const options = {
        method,
        headers: HEADERS,
    };
    if (body) {
        options.body = JSON.stringify(body);
    }
    const res = await fetch(url, options);
    if (!res.ok) {
        const text = await res.text();
        throw new Error(`HTTP ${res.status} from ${path}: ${text}`);
    }
    return res.status === 204 ? null : await res.json();
}

async function runNodeConformanceDemo() {
    console.log('==================================================================');
    console.log('      GlobalTalk AI — desi-node (v1.28.0) Conformance Demo        ');
    console.log('==================================================================');
    console.log(`Server URL: ${SERVER_URL}`);

    // 1. Text Translation (Single & Bulk)
    console.log('\n[1/7] Text Translation (Single & Bulk Array)...');
    const translateResult = await apiRequest('/v2/translate', 'POST', {
        text: ['Hello world!', 'GlobalTalk AI brings real-time communication to everyone.'],
        target_lang: 'DE',
        source_lang: 'EN',
        model_type: 'quality_optimized',
    });
    console.log('Translations:');
    translateResult.translations.forEach((t, idx) => {
        console.log(`  ${idx + 1}. [${t.detected_source_language} -> DE]: "${t.text}" (billed: ${t.billed_characters})`);
    });

    // 2. HTML Website Translation (Tag-Handling)
    console.log('\n[2/7] HTML Website Tag Handling (translate_website)...');
    const htmlResult = await apiRequest('/v2/translate', 'POST', {
        text: ['<h1>Welcome</h1><p>Learn more <a href="https://example.com">here</a>.</p>'],
        target_lang: 'FR',
        tag_handling: 'html',
    });
    console.log('Translated HTML:', htmlResult.translations[0].text);

    // 3. Desi Write: Rephrasing
    console.log('\n[3/7] Desi Write: Rephrasing (/v2/write/rephrase)...');
    const writeResult = await apiRequest('/v2/write/rephrase', 'POST', {
        text: ['we need to talk about this asap.'],
        target_lang: 'EN-US',
        writing_style: 'business',
        tone: 'confident',
    });
    console.log('Rephrased Improvement:', writeResult.improvements[0].text);

    // 4. Usage & Languages
    console.log('\n[4/7] Usage Quotas & Language Capabilities...');
    const usage = await apiRequest('/v2/usage');
    console.log(`  Characters: ${usage.character_count} / ${usage.character_limit}`);
    console.log(`  Documents:  ${usage.document_count} / ${usage.document_limit}`);

    const targetLangs = await apiRequest('/v2/languages?type=target');
    console.log(`  Supported Target Languages: ${targetLangs.length} available.`);

    // 5. v3 Multilingual Glossaries
    console.log('\n[5/7] v3 Multilingual Glossaries...');
    const glossary = await apiRequest('/v3/glossaries', 'POST', {
        name: 'Node Tech Terms',
        dictionaries: [
            {
                source_lang: 'EN',
                target_lang: 'DE',
                entries: { 'pipeline': 'Verarbeitungskette', 'framework': 'Rahmenwerk' },
            },
        ],
    });
    console.log(`  Created Glossary "${glossary.name}" (ID: ${glossary.glossary_id})`);

    // 6. v3 Style Rules & Custom Instructions
    console.log('\n[6/7] v3 Style Rules & Custom Instructions...');
    const styleRule = await apiRequest('/v3/style_rules', 'POST', {
        name: 'Corporate Tone',
        language: 'en',
        configured_rules: { style_and_tone: { formality: 'formal' } },
        custom_instructions: ['Use active voice', 'Maintain executive clarity'],
    });
    console.log(`  Created Style Rule "${styleRule.name}" (ID: ${styleRule.style_id})`);

    // 7. v3 Translation Memories
    console.log('\n[7/7] v3 Translation Memories...');
    const tmList = await apiRequest('/v3/translation_memories');
    console.log(`  Active Translation Memories: ${tmList.length} registered.`);

    console.log('\n==================================================================');
    console.log('✅ desi-node Conformance Verification: PASSED (All 7 Checks Ok)');
    console.log('==================================================================');
}

runNodeConformanceDemo().catch((err) => {
    console.error('[-] Demo failed:', err);
    process.exit(1);
});

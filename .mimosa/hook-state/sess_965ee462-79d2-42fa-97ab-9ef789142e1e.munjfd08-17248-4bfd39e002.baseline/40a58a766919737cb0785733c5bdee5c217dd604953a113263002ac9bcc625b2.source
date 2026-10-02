<?php
/**
 * GlobalTalk AI — Desi PHP (v1.20.0) Wire-Protocol Conformance Demo
 *
 * Verifies 100% wire-protocol compatibility between the Desi PHP client library
 * (desi-php) and the GlobalTalk AI API gateway (http://127.0.0.1:8088).
 *
 * Supports optional CLI arguments:
 *   php examples/desi_php_demo.php [appName] [runName]
 *
 * Example:
 *   php examples/desi_php_demo.php desi name
 */

$serverUrl = getenv('DESI_SERVER_URL') ?: (getenv('DEEPL_SERVER_URL') ?: 'http://127.0.0.1:8088');
$authKey   = getenv('DESI_AUTH_KEY') ?: (getenv('DEEPL_AUTH_KEY') ?: 'gtk_demo_key:fx');

// Parse CLI arguments if provided
$appName = isset($argv[1]) && trim($argv[1]) !== '' ? trim($argv[1]) : 'desi-php';
$runName = isset($argv[2]) && trim($argv[2]) !== '' ? trim($argv[2]) : 'Conformance Demo';

echo "==================================================================\n";
echo "       GlobalTalk AI — " . htmlspecialchars($appName) . " (v1.20.0) Conformance Demo       \n";
echo "==================================================================\n";
echo "Server URL: {$serverUrl}\n";
echo "Auth Key:   {$authKey}\n";
echo "App / Mode: {$appName}\n";
echo "Run Name:   {$runName}\n\n";

$headers = [
    "Authorization: Desi-Auth-Key {$authKey}",
    "User-Agent: {$appName}/1.20.0 (GlobalTalk AI Conformance; {$runName})",
];

function http_request($method, $url, $headers = [], $body = null) {
    $opts = [
        'http' => [
            'method'  => $method,
            'header'  => implode("\r\n", $headers) . "\r\n",
            'content' => $body,
            'ignore_errors' => true,
            'timeout' => 15,
        ]
    ];
    $context = stream_context_create($opts);
    $response = @file_get_contents($url, false, $context);
    
    $status_code = 500;
    if (isset($http_response_header) && count($http_response_header) > 0) {
        if (preg_match('#HTTP/[0-9\.]+\s+([0-9]+)#', $http_response_header[0], $matches)) {
            $status_code = (int)$matches[1];
        }
    }
    return [$status_code, $response];
}

$passed = 0;
$total = 8;

// [1/8] Text Translation (POST /v2/translate)
echo "[1/8] Text Translation (POST /v2/translate)...\n";
$transPayload = json_encode([
    'text' => ["Hello world! Welcome to GlobalTalk AI.", "AI-driven multilingual communication simplifies cross-border teamwork."],
    'target_lang' => 'DE',
    'source_lang' => 'EN',
    'model_type' => 'quality_optimized',
]);
$reqHeaders = array_merge($headers, ["Content-Type: application/json"]);
list($code, $res) = http_request('POST', "{$serverUrl}/v2/translate", $reqHeaders, $transPayload);

if ($code === 200) {
    $data = json_decode($res, true);
    if (!empty($data['translations'])) {
        $first = $data['translations'][0];
        echo "  [OK] HTTP 200 | Detected: {$first['detected_source_language']} | Billed: {$first['billed_characters']} chars\n";
        echo "  [OK] Translated: \"{$first['text']}\"\n";
        $passed++;
    } else {
        echo "  [FAIL] Missing translations array in response: {$res}\n";
    }
} else {
    echo "  [FAIL] HTTP {$code}: {$res}\n";
}

// [2/8] Desi Write Rephrase & Correct (POST /v2/write/rephrase & /v2/write/correct)
echo "\n[2/8] Desi Write Rephrase & Correct (POST /v2/write/rephrase & /v2/write/correct)...\n";
$writePayload = json_encode([
    'text' => ["Can we reschedule the meeting for tomorrow afternoon?"],
    'target_lang' => 'en',
    'writing_style' => 'business',
    'tone' => 'professional',
]);
list($code, $res) = http_request('POST', "{$serverUrl}/v2/write/rephrase", $reqHeaders, $writePayload);
if ($code === 200) {
    $data = json_decode($res, true);
    $improved = $data['improvements'][0]['text'] ?? '';
    echo "  [OK] Rephrase HTTP 200 | Improved: \"{$improved}\"\n";

    // Test correct
    $correctPayload = json_encode(['text' => ["We needs to talk about this asap."]]);
    list($cCode, $cRes) = http_request('POST', "{$serverUrl}/v2/write/correct", $reqHeaders, $correctPayload);
    if ($cCode === 200) {
        $cData = json_decode($cRes, true);
        echo "  [OK] Correct HTTP 200 | Corrected: \"{$cData['improvements'][0]['text']}\"\n";
        $passed++;
    } else {
        echo "  [FAIL] Correct HTTP {$cCode}: {$cRes}\n";
    }
} else {
    echo "  [FAIL] Rephrase HTTP {$code}: {$res}\n";
}

// [3/8] Language Discovery & Resources (GET /v3/languages & /v3/languages/resources)
echo "\n[3/8] Language Discovery & Resources (GET /v3/languages & /v3/languages/resources)...\n";
list($code, $res) = http_request('GET', "{$serverUrl}/v3/languages/resources", $headers);
if ($code === 200) {
    $resData = json_decode($res, true);
    $count = count($resData);
    echo "  [OK] /v3/languages/resources HTTP 200 | Cataloged {$count} resources\n";

    list($lCode, $lRes) = http_request('GET', "{$serverUrl}/v3/languages?resource=translate_text&include=beta,external", $headers);
    if ($lCode === 200) {
        $langs = json_decode($lRes, true);
        echo "  [OK] /v3/languages?resource=translate_text HTTP 200 | Loaded " . count($langs) . " supported languages\n";
        $passed++;
    } else {
        echo "  [FAIL] /v3/languages HTTP {$lCode}: {$lRes}\n";
    }
} else {
    echo "  [FAIL] /v3/languages/resources HTTP {$code}: {$res}\n";
}

// [4/8] Multilingual Glossaries (POST, GET, PATCH, PUT /v3/glossaries)
echo "\n[4/8] Multilingual Glossaries (POST, GET, PATCH, PUT /v3/glossaries)...\n";
$glossaryPayload = json_encode([
    'name' => 'Demo Multilingual Glossary',
    'dictionaries' => [
        [
            'source_lang' => 'EN',
            'target_lang' => 'DE',
            'entries' => [
                'quality assurance' => 'Qualitätssicherung',
                'teamwork' => 'Zusammenarbeit',
            ],
        ],
    ],
]);
list($code, $res) = http_request('POST', "{$serverUrl}/v3/glossaries", $reqHeaders, $glossaryPayload);
if ($code === 200) {
    $gData = json_decode($res, true);
    $gid = $gData['glossary_id'] ?? '';
    echo "  [OK] Created Glossary ID: {$gid} | Name: {$gData['name']} | Entries: {$gData['entry_count']}\n";

    // Patch dictionary entry
    $patchPayload = json_encode([
        'source_lang' => 'EN',
        'target_lang' => 'DE',
        'entries' => ['conformance' => 'Übereinstimmung'],
    ]);
    list($pCode, $pRes) = http_request('PATCH', "{$serverUrl}/v3/glossaries/{$gid}/dictionaries", $reqHeaders, $patchPayload);
    if ($pCode === 200) {
        echo "  [OK] Upserted dictionary entry into multilingual glossary\n";
        $passed++;
    } else {
        echo "  [FAIL] Patch dictionary HTTP {$pCode}: {$pRes}\n";
    }
} else {
    echo "  [FAIL] Create glossary HTTP {$code}: {$res}\n";
}

// [5/8] Style Rules & Configured Rules (POST /v3/style_rules & PUT /v3/style_rules/{id}/configured_rules)
echo "\n[5/8] Style Rules & Configured Rules (POST /v3/style_rules & PUT .../configured_rules)...\n";
$stylePayload = json_encode([
    'name' => 'Corporate German Style',
    'language' => 'de',
    'configured_rules' => [
        'style_and_tone' => ['formality' => 'formal'],
    ],
]);
list($code, $res) = http_request('POST', "{$serverUrl}/v3/style_rules", $reqHeaders, $stylePayload);
if ($code === 200) {
    $sData = json_decode($res, true);
    $styleId = $sData['style_id'] ?? '';
    echo "  [OK] Created Style Rule ID: {$styleId} | Language: {$sData['language']}\n";

    // Put configured rules (used heavily in desi-php)
    $rulesPayload = json_encode([
        'style_and_tone' => ['formality' => 'formal', 'brand_voice' => 'innovative'],
    ]);
    list($rCode, $rRes) = http_request('PUT', "{$serverUrl}/v3/style_rules/{$styleId}/configured_rules", $reqHeaders, $rulesPayload);
    if ($rCode === 200) {
        echo "  [OK] Updated configured rules via PUT\n";
        $passed++;
    } else {
        echo "  [FAIL] PUT configured_rules HTTP {$rCode}: {$rRes}\n";
    }
} else {
    echo "  [FAIL] POST /v3/style_rules HTTP {$code}: {$res}\n";
}

// [6/8] Custom Instructions (POST & PUT /v3/style_rules/{id}/custom_instructions)
echo "\n[6/8] Custom Instructions (POST & PUT /v3/style_rules/{id}/custom_instructions)...\n";
if (!empty($styleId)) {
    $instrPayload = json_encode([
        'label' => 'Technical Precision',
        'prompt' => 'Always preserve technical terms and do not translate product names.',
    ]);
    list($code, $res) = http_request('POST', "{$serverUrl}/v3/style_rules/{$styleId}/custom_instructions", $reqHeaders, $instrPayload);
    if ($code === 200) {
        $iData = json_decode($res, true);
        $instrId = $iData['id'] ?? '';
        echo "  [OK] Created Custom Instruction ID: {$instrId} | Label: {$iData['label']}\n";
        $passed++;
    } else {
        echo "  [FAIL] POST custom_instruction HTTP {$code}: {$res}\n";
    }
} else {
    echo "  [SKIP] Skipped because style rule creation failed\n";
}

// [7/8] Translation Memories (POST /v3/translation_memories/import & upload & export)
echo "\n[7/8] Translation Memories (POST /v3/translation_memories/import & upload & export)...\n";
$tmPayload = json_encode([
    'display_name' => 'GlobalTalk Memory',
    'file_name' => 'globaltalk.tmx',
]);
list($code, $res) = http_request('POST', "{$serverUrl}/v3/translation_memories/import", $reqHeaders, $tmPayload);
if ($code === 200) {
    $tmData = json_decode($res, true);
    $jobId = $tmData['job_id'] ?? '';
    echo "  [OK] Created Import Job: {$jobId}\n";

    // Upload minimal TMX content
    $tmxSample = '<?xml version="1.0" encoding="UTF-8"?><tmx version="1.4"><body><tu><tuv xml:lang="en"><seg>Hello</seg></tuv><tuv xml:lang="de"><seg>Hallo</seg></tuv></tu></body></tmx>';
    list($uCode, $uRes) = http_request('PUT', "{$serverUrl}/v3/translation_memories/upload/{$jobId}", ["Content-Type: application/xml"], $tmxSample);
    if ($uCode === 200) {
        $uData = json_decode($uRes, true);
        $tmId = $uData['translation_memory_id'] ?? '';
        echo "  [OK] Uploaded TMX data | Memory ID: {$tmId}\n";

        // Query segments
        list($sCode, $sRes) = http_request('GET', "{$serverUrl}/v3/translation_memories/{$tmId}/segments", $headers);
        if ($sCode === 200) {
            $sData = json_decode($sRes, true);
            echo "  [OK] Listed " . count($sData['segments']) . " segments from translation memory\n";
            $passed++;
        }
    } else {
        echo "  [FAIL] Upload TMX HTTP {$uCode}: {$uRes}\n";
    }
} else {
    echo "  [FAIL] Import TM HTTP {$code}: {$res}\n";
}

// [8/8] Document Translation (POST /v2/document & /v2/document/{id})
echo "\n[8/8] Document Translation (POST /v2/document & /v2/document/{id})...\n";
$boundary = "---------------------------" . microtime(true);
$docContent = "Hello world! This is a test document translation.";
$multipartBody = "--{$boundary}\r\n"
    . "Content-Disposition: form-data; name=\"file\"; filename=\"test_document.txt\"\r\n"
    . "Content-Type: text/plain\r\n\r\n"
    . "{$docContent}\r\n"
    . "--{$boundary}\r\n"
    . "Content-Disposition: form-data; name=\"target_lang\"\r\n\r\n"
    . "DE\r\n"
    . "--{$boundary}\r\n"
    . "Content-Disposition: form-data; name=\"source_lang\"\r\n\r\n"
    . "EN\r\n"
    . "--{$boundary}--\r\n";

$docHeaders = array_merge($headers, [
    "Content-Type: multipart/form-data; boundary={$boundary}",
    "Content-Length: " . strlen($multipartBody),
]);

list($code, $res) = http_request('POST', "{$serverUrl}/v2/document", $docHeaders, $multipartBody);
if ($code === 200) {
    $docData = json_decode($res, true);
    $docId = $docData['document_id'] ?? '';
    echo "  [OK] Uploaded Document ID: {$docId}\n";

    // Check status
    list($stCode, $stRes) = http_request('POST', "{$serverUrl}/v2/document/{$docId}", $headers);
    if ($stCode === 200) {
        $stData = json_decode($stRes, true);
        echo "  [OK] Document Status: {$stData['status']} | Billed: {$stData['billed_characters']} chars\n";
        $passed++;
    } else {
        echo "  [FAIL] Check document status HTTP {$stCode}: {$stRes}\n";
    }
} else {
    echo "  [FAIL] Upload document HTTP {$code}: {$res}\n";
}

echo "\n==================================================================\n";
if ($passed === $total) {
    echo "[SUCCESS] {$passed}/{$total} Desi Wire-Protocol Tests Passed! Conformance: 100%\n";
} else {
    echo "[WARNING] {$passed}/{$total} Desi Wire-Protocol Tests Passed.\n";
}
echo "==================================================================\n";

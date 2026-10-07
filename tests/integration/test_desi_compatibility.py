"""Integration tests for Desi API v2 and v3 standard conformance.

Validates that GlobalTalk AI provides exact response shapes and protocol support
expected by the official Desi Python SDK (desi-python v1.32.0).
"""
import pytest


@pytest.fixture(scope="module")
def client():
    from app.config import get_settings
    get_settings.cache_clear()
    import importlib
    import app.config as cfg
    importlib.reload(cfg)
    from app.main import create_app
    from starlette.testclient import TestClient
    with TestClient(create_app()) as c:
        yield c


def test_v2_translate_json(client):
    """Test POST /v2/translate with JSON body."""
    headers = {"Authorization": "Desi-Auth-Key test-key-12345:fx"}
    payload = {
        "text": ["Hello world", "Good morning"],
        "target_lang": "DE",
        "source_lang": "EN",
        "model_type": "quality_optimized",
    }
    resp = client.post("/v2/translate", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "translations" in data
    assert len(data["translations"]) == 2
    for t in data["translations"]:
        assert "text" in t
        assert "detected_source_language" in t
        assert "billed_characters" in t
        assert t["billed_characters"] > 0
        assert t["model_type_used"] == "quality_optimized"


def test_v2_translate_form_urlencoded(client):
    """Test POST /v2/translate with application/x-www-form-urlencoded (used by CLI and standard requests)."""
    headers = {"Authorization": "Desi-Auth-Key test-key-12345:fx"}
    form_data = {
        "text": "Hello world",
        "target_lang": "FR",
    }
    resp = client.post("/v2/translate", data=form_data, headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "translations" in data
    assert len(data["translations"]) == 1
    item = data["translations"][0]
    assert item["billed_characters"] == len("Hello world")
    assert item["detected_source_language"] == "EN"


def test_v2_write_rephrase_and_correct(client):
    """Test Desi Write API: /v2/write/rephrase and /v2/write/correct."""
    headers = {"Authorization": "Desi-Auth-Key test-key-12345:fx"}

    # 1. Rephrase
    rephrase_resp = client.post(
        "/v2/write/rephrase",
        json={"text": ["This is a draft sentence."], "target_lang": "EN-US", "writing_style": "business", "tone": "confident"},
        headers=headers,
    )
    assert rephrase_resp.status_code == 200, rephrase_resp.text
    rep_data = rephrase_resp.json()
    assert "improvements" in rep_data
    assert len(rep_data["improvements"]) == 1
    assert "text" in rep_data["improvements"][0]
    assert rep_data["improvements"][0]["target_language"] == "EN-US"

    # 2. Correct (v1.32.0 endpoint)
    correct_resp = client.post(
        "/v2/write/correct",
        json={"text": "They goes to school yesterday.", "target_lang": "EN"},
        headers=headers,
    )
    assert correct_resp.status_code == 200, correct_resp.text
    corr_data = correct_resp.json()
    assert "improvements" in corr_data
    assert len(corr_data["improvements"]) == 1
    assert "text" in corr_data["improvements"][0]


def test_v2_usage(client):
    """Test GET /v2/usage returns character, document, and team document metrics."""
    headers = {"Authorization": "Desi-Auth-Key test-key-12345:fx"}
    resp = client.get("/v2/usage", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "character_count" in data
    assert "character_limit" in data
    assert "document_count" in data
    assert "document_limit" in data
    assert "team_document_count" in data
    assert "team_document_limit" in data


def test_v2_languages(client):
    """Test GET /v2/languages differentiating source vs target languages."""
    # Source languages
    src_resp = client.get("/v2/languages?type=source")
    assert src_resp.status_code == 200
    src_langs = src_resp.json()
    assert any(lang["language"] == "DE" for lang in src_langs)
    # Target languages
    tgt_resp = client.get("/v2/languages?type=target")
    assert tgt_resp.status_code == 200
    tgt_langs = tgt_resp.json()
    german = next(lang for lang in tgt_langs if lang["language"] == "DE")
    assert german["supports_formality"] is True

    # Glossary language pairs
    glp_resp = client.get("/v2/glossary-language-pairs")
    assert glp_resp.status_code == 200
    glp = glp_resp.json()
    assert "supported_languages" in glp
    assert any(p["source_lang"] == "EN" and p["target_lang"] == "DE" for p in glp["supported_languages"])


def test_v2_glossaries_lifecycle(client):
    """Test v2 monolingual glossaries CRUD."""
    headers = {"Authorization": "Desi-Auth-Key test-key-12345:fx"}

    # 1. Create
    create_resp = client.post(
        "/v2/glossaries",
        data={
            "name": "Test Monolingual Glossary",
            "source_lang": "EN",
            "target_lang": "DE",
            "entries": "artist\tMaler\nprize\tGewinn",
            "entries_format": "tsv",
        },
        headers=headers,
    )
    assert create_resp.status_code == 200, create_resp.text
    created = create_resp.json()
    gid = created["glossary_id"]
    assert created["entry_count"] == 2
    assert created["ready"] is True

    # 2. List
    list_resp = client.get("/v2/glossaries", headers=headers)
    assert list_resp.status_code == 200
    assert any(g["glossary_id"] == gid for g in list_resp.json()["glossaries"])

    # 3. Get
    get_resp = client.get(f"/v2/glossaries/{gid}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Test Monolingual Glossary"

    # 4. Entries TSV
    entries_resp = client.get(f"/v2/glossaries/{gid}/entries", headers=headers)
    assert entries_resp.status_code == 200
    assert "artist\tMaler" in entries_resp.text

    # 5. Delete
    del_resp = client.delete(f"/v2/glossaries/{gid}", headers=headers)
    assert del_resp.status_code == 204


def test_v3_multilingual_glossaries(client):
    """Test v3 multilingual glossaries CRUD and dictionary operations."""
    headers = {"Authorization": "Desi-Auth-Key test-key-12345:fx"}

    # 1. Create with multiple dictionaries
    payload = {
        "name": "Company Terms v3",
        "dictionaries": [
            {
                "source_lang": "EN",
                "target_lang": "DE",
                "entries": {"artist": "Maler", "prize": "Gewinn"},
            },
            {
                "source_lang": "EN",
                "target_lang": "FR",
                "entries": {"artist": "Artiste"},
            },
        ],
    }
    create_resp = client.post("/v3/glossaries", json=payload, headers=headers)
    assert create_resp.status_code == 200, create_resp.text
    created = create_resp.json()
    gid = created["glossary_id"]
    assert created["name"] == "Company Terms v3"
    assert created["entry_count"] == 3
    assert len(created["dictionaries"]) == 2

    # 2. Get glossary
    get_resp = client.get(f"/v3/glossaries/{gid}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["glossary_id"] == gid

    # 3. Update glossary name
    patch_resp = client.patch(f"/v3/glossaries/{gid}", json={"name": "Global Terms v3"}, headers=headers)
    assert patch_resp.status_code == 200
    assert patch_resp.json()["name"] == "Global Terms v3"

    # 4. Get dictionary entries
    entries_resp = client.get(f"/v3/glossaries/{gid}/entries?source_lang=EN&target_lang=DE", headers=headers)
    assert entries_resp.status_code == 200
    entries_data = entries_resp.json()
    assert len(entries_data["dictionaries"]) == 1
    assert entries_data["dictionaries"][0]["entries"]["artist"] == "Maler"

    # 5. Update dictionary entries (upsert)
    update_dict_resp = client.patch(
        f"/v3/glossaries/{gid}/dictionaries",
        json={"source_lang": "EN", "target_lang": "DE", "entries": {"hello": "hallo"}},
        headers=headers,
    )
    assert update_dict_resp.status_code == 200

    # 6. Replace dictionary entries
    replace_dict_resp = client.put(
        f"/v3/glossaries/{gid}/dictionaries",
        json={"source_lang": "EN", "target_lang": "DE", "entries": {"farewell": "Lebewohl"}},
        headers=headers,
    )
    assert replace_dict_resp.status_code == 200

    # 7. Delete dictionary
    del_dict_resp = client.delete(f"/v3/glossaries/{gid}/dictionaries?source_lang=EN&target_lang=FR", headers=headers)
    assert del_dict_resp.status_code == 204

    # 8. Delete glossary
    del_resp = client.delete(f"/v3/glossaries/{gid}", headers=headers)
    assert del_resp.status_code == 204


def test_v3_style_rules_and_custom_instructions(client):
    """Test v3 style rules CRUD and custom instructions."""
    headers = {"Authorization": "Desi-Auth-Key test-key-12345:fx"}

    # 1. Create style rule
    rule_payload = {
        "name": "Corporate Formal",
        "language": "en",
        "configured_rules": {"style_and_tone": {"formality": "formal"}},
        "custom_instructions": [],
    }
    create_resp = client.post("/v3/style_rules", json=rule_payload, headers=headers)
    assert create_resp.status_code == 200, create_resp.text
    rule = create_resp.json()
    style_id = rule["style_id"]
    assert rule["name"] == "Corporate Formal"

    # 2. List style rules
    list_resp = client.get("/v3/style_rules?detailed=true", headers=headers)
    assert list_resp.status_code == 200
    assert any(r["style_id"] == style_id for r in list_resp.json())

    # 3. Add custom instruction
    instr_resp = client.post(
        f"/v3/style_rules/{style_id}/custom_instructions",
        json={"label": "Polite tone", "prompt": "Always use polite and formal phrases"},
        headers=headers,
    )
    assert instr_resp.status_code == 200
    instr_id = instr_resp.json()["id"]

    # 4. Get custom instruction
    get_instr_resp = client.get(f"/v3/style_rules/{style_id}/custom_instructions/{instr_id}", headers=headers)
    assert get_instr_resp.status_code == 200
    assert get_instr_resp.json()["label"] == "Polite tone"

    # 5. Delete custom instruction & style rule
    del_instr = client.delete(f"/v3/style_rules/{style_id}/custom_instructions/{instr_id}", headers=headers)
    assert del_instr.status_code == 204
    del_rule = client.delete(f"/v3/style_rules/{style_id}", headers=headers)
    assert del_rule.status_code == 204


def test_v3_translation_memories(client):
    """Test v3 translation memories import, segments, export, and delete."""
    headers = {"Authorization": "Desi-Auth-Key test-key-12345:fx"}

    # 1. Import job creation
    import_resp = client.post(
        "/v3/translation_memories/import",
        json={"file_name": "contract.tmx", "display_name": "Contract TM"},
        headers=headers,
    )
    assert import_resp.status_code == 200
    job_id = import_resp.json()["job_id"]

    # 2. Upload file
    dummy_tmx = b"<tmx>sample content</tmx>"
    upload_resp = client.put(f"/v3/translation_memories/upload/{job_id}", content=dummy_tmx, headers=headers)
    assert upload_resp.status_code == 200

    # 3. Check job status
    job_resp = client.get(f"/v3/translation_memories/jobs/{job_id}", headers=headers)
    assert job_resp.status_code == 200
    tm_id = job_resp.json()["result"]["translation_memory_id"]

    # 4. List and get TM
    tm_list = client.get("/v3/translation_memories", headers=headers)
    assert tm_list.status_code == 200
    assert any(tm["translation_memory_id"] == tm_id for tm in tm_list.json())

    # 5. List segments
    segments_resp = client.get(f"/v3/translation_memories/{tm_id}/segments", headers=headers)
    assert segments_resp.status_code == 200
    assert len(segments_resp.json()["segments"]) > 0

    # 6. Export TM
    export_resp = client.post("/v3/translation_memories/export", json={"translation_memory_id": tm_id}, headers=headers)
    assert export_resp.status_code == 200
    export_job_id = export_resp.json()["job_id"]

    # 7. Download export
    download_resp = client.get(f"/v3/translation_memories/download/{export_job_id}", headers=headers)
    assert download_resp.status_code == 200
    assert "<tmx" in download_resp.text

    # 8. Delete TM
    del_resp = client.delete(f"/v3/translation_memories/{tm_id}", headers=headers)
    assert del_resp.status_code == 204


def test_v2_document_translation(client):
    """Test /v2/document upload, status check, and result download."""
    headers = {"Authorization": "Desi-Auth-Key test-key-12345:fx"}

    # 1. Upload document
    files = {"file": ("sample.txt", b"Hello, this is a test document.", "text/plain")}
    data = {"target_lang": "DE", "source_lang": "EN"}
    upload_resp = client.post("/v2/document", files=files, data=data, headers=headers)
    assert upload_resp.status_code == 200, upload_resp.text
    doc_info = upload_resp.json()
    doc_id = doc_info["document_id"]
    doc_key = doc_info["document_key"]

    # 2. Check status
    status_resp = client.post(f"/v2/document/{doc_id}", data={"document_key": doc_key}, headers=headers)
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["status"] == "done"

    # 3. Download result
    res_resp = client.post(f"/v2/document/{doc_id}/result", data={"document_key": doc_key}, headers=headers)
    assert res_resp.status_code == 200
    assert len(res_resp.content) > 0


def test_custom_instructions_and_glossary_ids_validation(client):
    """Test Desi v1.31-v1.32 parameter validation rules."""
    headers = {"Authorization": "Desi-Auth-Key test-key-12345:fx"}

    # 1. Custom instructions valid call -> auto-selects quality_optimized
    resp = client.post(
        "/v2/translate",
        json={"text": "Hello world", "target_lang": "DE", "custom_instructions": ["Be concise"]},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["translations"][0]["model_type_used"] == "quality_optimized"

    # 2. Custom instructions + latency_optimized -> 400
    bad_resp = client.post(
        "/v2/translate",
        json={
            "text": "Hello world",
            "target_lang": "DE",
            "custom_instructions": ["Be concise"],
            "model_type": "latency_optimized",
        },
        headers=headers,
    )
    assert bad_resp.status_code == 400

    # 3. glossary + glossary_ids conflict -> 400
    bad_gloss = client.post(
        "/v2/translate",
        json={
            "text": "Hello world",
            "target_lang": "DE",
            "source_lang": "EN",
            "glossary": "g-1",
            "glossary_ids": ["g-2"],
        },
        headers=headers,
    )
    assert bad_gloss.status_code == 400

    # 4. glossary_ids without source_lang -> 400
    bad_src = client.post(
        "/v2/translate",
        json={"text": "Hello world", "target_lang": "DE", "glossary_ids": ["g-1"]},
        headers=headers,
    )
    assert bad_src.status_code == 400


def test_v3_languages_and_resources_conformance(client):
    """Test /v3/languages/resources catalog and per-resource /v3/languages capability filters conforming to desi-php."""
    headers = {"Authorization": "Desi-Auth-Key test-key-12345:fx"}

    # 1. GET /v3/languages/resources returns list of resource features
    res_resp = client.get("/v3/languages/resources", headers=headers)
    assert res_resp.status_code == 200, res_resp.text
    resources = res_resp.json()
    assert isinstance(resources, list)
    resource_names = {r["resource"] for r in resources}
    assert "translate_text" in resource_names
    assert "translate_document" in resource_names
    assert "glossaries" in resource_names
    assert "write" in resource_names
    assert "style_rules" in resource_names
    assert "translation_memories" in resource_names

    # Check features on translate_text
    tt = next(r for r in resources if r["resource"] == "translate_text")
    assert "formality" in tt["features"]
    assert tt["features"]["formality"]["needs_target_support"] is True

    # 2. GET /v3/languages?resource=translate_text
    lang_resp = client.get("/v3/languages?resource=translate_text", headers=headers)
    assert lang_resp.status_code == 200, lang_resp.text
    langs = lang_resp.json()
    assert isinstance(langs, list)
    assert len(langs) > 0
    de_lang = next(lang for lang in langs if lang["code"] == "de")
    assert de_lang["usable_as_source"] is True
    assert de_lang["usable_as_target"] is True
    assert de_lang["supports_formality"] is True
    assert "formality" in de_lang["features"]

    # 3. GET /v3/languages?resource=translate_text&include=beta,external
    inc_resp = client.get("/v3/languages?resource=translate_text&include=beta,external", headers=headers)
    assert inc_resp.status_code == 200
    inc_langs = inc_resp.json()
    assert any(lang["code"] == "la" and lang["beta"] is True for lang in inc_langs)
    assert any(lang["code"] == "sa" and lang["external"] is True for lang in inc_langs)


def test_v3_style_rules_configured_rules_and_custom_instruction_put(client):
    """Test PUT /v3/style_rules/{id}/configured_rules and PUT /v3/style_rules/{id}/custom_instructions/{id} conforming to desi-php."""
    headers = {"Authorization": "Desi-Auth-Key test-key-12345:fx"}

    # 1. Create rule
    create_resp = client.post(
        "/v3/style_rules",
        json={"name": "PHP Style Rule", "language": "de", "configured_rules": {}},
        headers=headers,
    )
    assert create_resp.status_code == 200
    style_id = create_resp.json()["style_id"]

    try:
        # 2. PUT /v3/style_rules/{style_id}/configured_rules
        put_rules_resp = client.put(
            f"/v3/style_rules/{style_id}/configured_rules",
            json={"numbers": "words", "dates": "dmy"},
            headers=headers,
        )
        assert put_rules_resp.status_code == 200
        assert put_rules_resp.json()["numbers"] == "words"

        # Verify through GET style rule
        get_rule_resp = client.get(f"/v3/style_rules/{style_id}", headers=headers)
        assert get_rule_resp.status_code == 200
        assert get_rule_resp.json()["configured_rules"]["numbers"] == "words"

        # 3. POST and PUT custom instruction
        post_instr = client.post(
            f"/v3/style_rules/{style_id}/custom_instructions",
            json={"label": "Greeting rule", "prompt": "Say hello"},
            headers=headers,
        )
        assert post_instr.status_code == 200
        instr_id = post_instr.json()["id"]

        put_instr = client.put(
            f"/v3/style_rules/{style_id}/custom_instructions/{instr_id}",
            json={"label": "Updated Greeting rule", "prompt": "Say greetings warmly"},
            headers=headers,
        )
        assert put_instr.status_code == 200
        assert put_instr.json()["label"] == "Updated Greeting rule"
    finally:
        client.delete(f"/v3/style_rules/{style_id}", headers=headers)

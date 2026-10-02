// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

package com.desi.api;

import com.desi.api.http.JsonUtils;
import org.junit.jupiter.api.Test;

import java.util.*;

import static org.junit.jupiter.api.Assertions.*;

public class JsonUtilsTest {

    @Test
    public void testSerialization() {
        Map<String, Object> map = new LinkedHashMap<>();
        map.put("text", "नमस्ते");
        map.put("honorific", "formal");
        map.put("count", 42);
        map.put("active", true);

        String json = JsonUtils.toJson(map);
        assertTrue(json.contains("\"text\":\"नमस्ते\""));
        assertTrue(json.contains("\"honorific\":\"formal\""));
        assertTrue(json.contains("\"count\":42"));
        assertTrue(json.contains("\"active\":true"));
    }

    @Test
    public void testParsingObject() {
        String json = "{\"text\":\"Hello World\",\"billed_characters\":11,\"success\":true}";
        Map<String, Object> map = JsonUtils.parseJsonObject(json);

        assertEquals("Hello World", map.get("text"));
        assertEquals(11L, ((Number) map.get("billed_characters")).longValue());
        assertEquals(Boolean.TRUE, map.get("success"));
    }

    @Test
    public void testParsingArray() {
        String json = "[\"Devanagari\",\"Bengali\",\"Tamil\"]";
        List<Object> list = JsonUtils.parseJsonArray(json);

        assertEquals(3, list.size());
        assertEquals("Devanagari", list.get(0));
        assertEquals("Bengali", list.get(1));
        assertEquals("Tamil", list.get(2));
    }

    @Test
    public void testLanguageCodeIndicCheck() {
        assertTrue(LanguageCode.isIndic(LanguageCode.HINDI));
        assertTrue(LanguageCode.isIndic(LanguageCode.TAMIL));
        assertTrue(LanguageCode.isIndic(LanguageCode.BENGALI));
        assertFalse(LanguageCode.isIndic(LanguageCode.GERMAN));
        assertFalse(LanguageCode.isIndic(LanguageCode.FRENCH));
    }
}

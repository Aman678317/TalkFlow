// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

package com.desi.api;

import com.desi.api.model.DesiTranslateOptions;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

public class DesiTranslateOptionsTest {

    @Test
    public void testDefaultOptions() {
        DesiTranslateOptions opt = new DesiTranslateOptions();
        assertEquals(DesiHonorific.FORMAL, opt.getHonorific());
        assertEquals(DesiDomain.GENERAL, opt.getDomain());
        assertEquals(DesiScript.DEVANAGARI, opt.getTargetScript());
        assertFalse(opt.isRespectfulSuffix());
    }

    @Test
    public void testCustomOptions() {
        DesiTranslateOptions opt = new DesiTranslateOptions()
                .setHonorific(DesiHonorific.RESPECTFUL)
                .setDomain(DesiDomain.BUSINESS)
                .setTargetScript(DesiScript.GURMUKHI)
                .setRespectfulSuffix(true);

        assertEquals(DesiHonorific.RESPECTFUL, opt.getHonorific());
        assertEquals(DesiDomain.BUSINESS, opt.getDomain());
        assertEquals(DesiScript.GURMUKHI, opt.getTargetScript());
        assertTrue(opt.isRespectfulSuffix());
    }
}

// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

package com.desi.api;

import java.util.Collections;
import java.util.HashSet;
import java.util.Set;

/**
 * Standard ISO language code constants for all world languages and Indic (Desi) languages.
 */
public final class LanguageCode {
    private LanguageCode() {}

    // ----------------------------------------------------------------------------------------------
    // 22 Official Eighth Schedule Indian (Desi) Languages
    // ----------------------------------------------------------------------------------------------
    public static final String HINDI = "hi";
    public static final String BENGALI = "bn";
    public static final String MARATHI = "mr";
    public static final String TELUGU = "te";
    public static final String TAMIL = "ta";
    public static final String GUJARATI = "gu";
    public static final String URDU = "ur";
    public static final String KANNADA = "kn";
    public static final String ODIA = "or";
    public static final String MALAYALAM = "ml";
    public static final String PUNJABI = "pa";
    public static final String ASSAMESE = "as";
    public static final String SANSKRIT = "sa";
    public static final String NEPALI = "ne";
    public static final String MAITHILI = "mai";
    public static final String SANTALI = "sat";
    public static final String KASHMIRI = "ks";
    public static final String SINDHI = "sd";
    public static final String KONKANI = "kok";
    public static final String DOGRI = "doi";
    public static final String MANIPURI = "mni";
    public static final String BODO = "brx";

    // ----------------------------------------------------------------------------------------------
    // Major World Languages: Europe, Americas, Asia, Middle East, and Africa
    // ----------------------------------------------------------------------------------------------
    public static final String AFRIKAANS = "af";
    public static final String ALBANIAN = "sq";
    public static final String AMHARIC = "am";
    public static final String ARABIC = "ar";
    public static final String ARMENIAN = "hy";
    public static final String AZERBAIJANI = "az";
    public static final String BASQUE = "eu";
    public static final String BELARUSIAN = "be";
    public static final String BOSNIAN = "bs";
    public static final String BULGARIAN = "bg";
    public static final String BURMESE = "my";
    public static final String CATALAN = "ca";
    public static final String CHINESE = "zh";
    public static final String CHINESE_SIMPLIFIED = "zh-Hans";
    public static final String CHINESE_TRADITIONAL = "zh-Hant";
    public static final String CROATIAN = "hr";
    public static final String CZECH = "cs";
    public static final String DANISH = "da";
    public static final String DUTCH = "nl";
    public static final String ENGLISH = "en";
    public static final String ENGLISH_BRITISH = "en-GB";
    public static final String ENGLISH_AMERICAN = "en-US";
    public static final String ESPERANTO = "eo";
    public static final String ESTONIAN = "et";
    public static final String FINNISH = "fi";
    public static final String FRENCH = "fr";
    public static final String GALICIAN = "gl";
    public static final String GEORGIAN = "ka";
    public static final String GERMAN = "de";
    public static final String GREEK = "el";
    public static final String HAITIAN_CREOLE = "ht";
    public static final String HAUSA = "ha";
    public static final String HEBREW = "he";
    public static final String HUNGARIAN = "hu";
    public static final String ICELANDIC = "is";
    public static final String IGBO = "ig";
    public static final String INDONESIAN = "id";
    public static final String IRISH = "ga";
    public static final String ITALIAN = "it";
    public static final String JAPANESE = "ja";
    public static final String JAVANESE = "jv";
    public static final String KAZAKH = "kk";
    public static final String KHMER = "km";
    public static final String KOREAN = "ko";
    public static final String KURDISH = "ku";
    public static final String LAO = "lo";
    public static final String LATIN = "la";
    public static final String LATVIAN = "lv";
    public static final String LITHUANIAN = "lt";
    public static final String MACEDONIAN = "mk";
    public static final String MALAGASY = "mg";
    public static final String MALAY = "ms";
    public static final String MALTESE = "mt";
    public static final String MAORI = "mi";
    public static final String MONGOLIAN = "mn";
    public static final String NORWEGIAN = "nb";
    public static final String NORWEGIAN_BOKMAL = "nb";
    public static final String NORWEGIAN_NYNORSK = "nn";
    public static final String PASHTO = "ps";
    public static final String PERSIAN = "fa";
    public static final String POLISH = "pl";
    public static final String PORTUGUESE = "pt";
    public static final String PORTUGUESE_BRAZILIAN = "pt-BR";
    public static final String PORTUGUESE_EUROPEAN = "pt-PT";
    public static final String ROMANIAN = "ro";
    public static final String RUSSIAN = "ru";
    public static final String SAMOAN = "sm";
    public static final String SERBIAN = "sr";
    public static final String SINHALA = "si";
    public static final String SLOVAK = "sk";
    public static final String SLOVENIAN = "sl";
    public static final String SOMALI = "so";
    public static final String SPANISH = "es";
    public static final String SWAHILI = "sw";
    public static final String SWEDISH = "sv";
    public static final String TAGALOG = "tl";
    public static final String TAJIK = "tg";
    public static final String THAI = "th";
    public static final String TURKISH = "tr";
    public static final String TURKMEN = "tk";
    public static final String UKRAINIAN = "uk";
    public static final String UZBEK = "uz";
    public static final String VIETNAMESE = "vi";
    public static final String WELSH = "cy";
    public static final String XHOSA = "xh";
    public static final String YIDDISH = "yi";
    public static final String YORUBA = "yo";
    public static final String ZULU = "zu";

    private static final Set<String> INDIC_CODES;

    static {
        Set<String> indic = new HashSet<>();
        indic.add("hi"); indic.add("bn"); indic.add("mr"); indic.add("te");
        indic.add("ta"); indic.add("gu"); indic.add("ur"); indic.add("kn");
        indic.add("or"); indic.add("ml"); indic.add("pa"); indic.add("as");
        indic.add("sa"); indic.add("ne"); indic.add("mai"); indic.add("sat");
        indic.add("ks"); indic.add("sd"); indic.add("kok"); indic.add("doi");
        indic.add("mni"); indic.add("brx");
        INDIC_CODES = Collections.unmodifiableSet(indic);
    }

    /**
     * Checks if a given language code represents an Indian / Indic (Desi) language.
     */
    public static boolean isIndic(String code) {
        if (code == null) return false;
        String base = removeRegionalVariant(code).toLowerCase();
        return INDIC_CODES.contains(base);
    }

    /**
     * Standardizes language code format (e.g. "en-us" -> "en-US", "hi" -> "hi").
     */
    public static String standardize(String langCode) {
        if (langCode == null || langCode.trim().isEmpty()) {
            return "";
        }
        String[] parts = langCode.trim().split("[-_]");
        if (parts.length == 1) {
            return parts[0].toLowerCase();
        }
        if (parts.length == 2) {
            if (parts[1].equalsIgnoreCase("hans") || parts[1].equalsIgnoreCase("hant")) {
                return parts[0].toLowerCase() + "-" + Character.toUpperCase(parts[1].charAt(0)) + parts[1].substring(1).toLowerCase();
            }
            return parts[0].toLowerCase() + "-" + parts[1].toUpperCase();
        }
        return langCode;
    }

    /**
     * Strips regional or script variants (e.g. "en-US" -> "en", "zh-Hant" -> "zh").
     */
    public static String removeRegionalVariant(String langCode) {
        if (langCode == null || langCode.trim().isEmpty()) {
            return "";
        }
        int dashIdx = langCode.indexOf('-');
        if (dashIdx != -1) {
            return langCode.substring(0, dashIdx).toLowerCase();
        }
        int underscoreIdx = langCode.indexOf('_');
        if (underscoreIdx != -1) {
            return langCode.substring(0, underscoreIdx).toLowerCase();
        }
        return langCode.toLowerCase();
    }
}

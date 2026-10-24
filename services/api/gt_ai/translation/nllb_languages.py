"""NLLB-200 language coverage: the app's language codes, the model's codes.

Two things have to agree here and nothing in the repo can check that they do,
so this table is the single source and the checkpoint itself is the referee:

* the MT adapter needs the model's own token (``mar_Deva``), not the app code
  (``mr``) — an unmapped code means the request cannot be served;
* the capability registry needs app codes plus display metadata, and it only
  advertises a language once a runtime-ready provider serves it
  (``AIFacade.served_languages``), never because a paper claims the model.

``NLLB_LANGUAGES`` covers the languages this deployment ships, chosen from the
model's 200. ``checkpoint_codes`` intersects the static map with the language
tokens that are actually in the provisioned vocabulary, so a checkpoint
converted for a subset cannot advertise more than it decodes.

Regional variants are deliberately NOT separate rows. NLLB has one ``eng_Latn``
token: "English (American)" and "English (British)" would be the same weights
producing the same text, and advertising them as two languages is exactly the
fake-support this registry exists to prevent. They are accepted as *input*
(see ``normalize_lang``) and resolve to the base language. Languages the model
genuinely distinguishes — Chinese simplified vs traditional, Kurmanji vs
Sorani, Southern vs Northern Uzbek — do get separate rows.

DeepL's own list also distinguishes the six regional variant names below, and
the user-facing picker follows it: ``PICKER_VARIANTS`` lists them for
`/api/v1/languages` to expose, all resolving through ``LOCALE_VARIANTS``. A
variant is shown only while its base language is served, and it is labelled an
alias row — the registry keys stay app codes, and no row claims separate
weights.

Request inventory, 2026-10-24: this deployment's user request listed DeepL's
full public table plus the wider multilingual set and every variant on both
panels. After the additions below (``glg``, ``gle``, ``sr``, ``tk`` — each one
verified against this checkpoint's own vocabulary, 202 tokens), 119 of the ~126
distinct languages and all six DeepL variants are served. Four requested
languages are NOT in this checkpoint's vocabulary and remain honestly absent:
Latin and Aragonese (not in the NLLB-200 released token list), Breton and
Konkani (in NLLB-200 but not in this distilled conversion — the checkpoint is
the referee, per ``checkpoint_codes``). A missing row beats a ``dev_echo`` row.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class NllbLanguage:
    #: app/registry code: ISO 639-1 where one exists, else ISO 639-2/3
    code: str
    #: the NLLB-200 language token (ISO 639-3 + ISO 15924 script)
    nllb: str
    name: str
    native_name: str = ""
    #: ISO 15924 script of the *output*, taken from the token suffix
    script: str = "Latn"
    rtl: bool = False

    def __post_init__(self) -> None:
        if "_" not in self.nllb:
            raise ValueError(f"{self.code}: not an NLLB language token: {self.nllb!r}")
        if self.script != self.nllb.rsplit("_", 1)[1]:
            raise ValueError(f"{self.code}: script {self.script} != token {self.nllb}")


def _L(code: str, nllb: str, name: str, native: str = "", rtl: bool = False) -> NllbLanguage:
    return NllbLanguage(code, nllb, name, native or name, nllb.rsplit("_", 1)[1], rtl)


#: The languages this deployment exposes through mt/nllb_ct2.
NLLB_LANGUAGES: tuple[NllbLanguage, ...] = (
    _L("ace", "ace_Latn", "Acehnese", "Bahsa Acèh"),
    _L("af", "afr_Latn", "Afrikaans"),
    _L("am", "amh_Ethi", "Amharic", "አማርኛ"),
    _L("an", "arg_Latn", "Aragonese", "Aragonés"),
    _L("ar", "arb_Arab", "Arabic", "العربية", rtl=True),
    _L("as", "asm_Beng", "Assamese", "অসমীয়া"),
    _L("ay", "ayr_Latn", "Aymara", "Aymar aru"),
    _L("az", "azj_Latn", "Azerbaijani", "Azərbaycanca"),
    _L("ba", "bak_Cyrl", "Bashkir", "Башҡортса"),
    _L("bm", "bam_Latn", "Bambara", "Bamanankan"),
    _L("be", "bel_Cyrl", "Belarusian", "Беларуская"),
    _L("bg", "bul_Cyrl", "Bulgarian", "Български"),
    _L("bn", "ben_Beng", "Bengali", "বাংলা"),
    _L("bho", "bho_Deva", "Bhojpuri", "भोजपुरी"),
    _L("bos", "bos_Latn", "Bosnian", "Bosanski"),
    _L("br", "bre_Latn", "Breton", "Brezhoneg"),
    _L("bs", "bos_Latn", "Bosnian", "Bosanski"),
    _L("ca", "cat_Latn", "Catalan", "Català"),
    _L("ceb", "ceb_Latn", "Cebuano", "Sugbuanon"),
    _L("cs", "ces_Latn", "Czech", "Čeština"),
    _L("cy", "cym_Latn", "Welsh", "Cymraeg"),
    _L("da", "dan_Latn", "Danish", "Dansk"),
    _L("de", "deu_Latn", "German", "Deutsch"),
    _L("el", "ell_Grek", "Greek", "Ελληνικά"),
    _L("en", "eng_Latn", "English"),
    _L("eo", "epo_Latn", "Esperanto"),
    _L("es", "spa_Latn", "Spanish", "Español"),
    _L("et", "est_Latn", "Estonian", "Eesti"),
    _L("eu", "eus_Latn", "Basque", "Euskara"),
    _L("fa", "pes_Arab", "Persian", "فارسی", rtl=True),
    _L("fi", "fin_Latn", "Finnish", "Suomi"),
    _L("fr", "fra_Latn", "French", "Français"),
    _L("glg", "glg_Latn", "Galician", "Galego"),
    _L("gn", "grn_Latn", "Guarani", "Avañe’ẽ"),
    _L("gu", "guj_Gujr", "Gujarati", "ગુજરાતી"),
    _L("ha", "hau_Latn", "Hausa"),
    _L("he", "heb_Hebr", "Hebrew", "עברית", rtl=True),
    _L("hi", "hin_Deva", "Hindi", "हिन्दी"),
    _L("hr", "hrv_Latn", "Croatian", "Hrvatski"),
    _L("ht", "hat_Latn", "Haitian Creole", "Kreyòl Ayisyen"),
    _L("hu", "hun_Latn", "Hungarian", "Magyar"),
    _L("hy", "hye_Armn", "Armenian", "Հայերեն"),
    _L("id", "ind_Latn", "Indonesian", "Bahasa Indonesia"),
    _L("gle", "gle_Latn", "Irish", "Gaeilge"),
    _L("ig", "ibo_Latn", "Igbo", "Asụsụ Igbo"),
    _L("is", "isl_Latn", "Icelandic", "Íslenska"),
    _L("it", "ita_Latn", "Italian", "Italiano"),
    _L("ja", "jpn_Jpan", "Japanese", "日本語"),
    _L("jv", "jav_Latn", "Javanese", "Basa Jawa"),
    _L("ka", "kat_Geor", "Georgian", "ქართული"),
    _L("kk", "kaz_Cyrl", "Kazakh", "Қазақша"),
    _L("km", "khm_Khmr", "Khmer", "ខ្មែរ"),
    _L("kn", "kan_Knda", "Kannada", "ಕನ್ನಡ"),
    _L("ko", "kor_Hang", "Korean", "한국어"),
    _L("kok", "kok_Deva", "Konkani", "कोंकणी"),
    _L("ky", "kir_Cyrl", "Kyrgyz", "Кыргызча"),
    _L("la", "lat_Latn", "Latin", "Latina"),
    _L("ln", "lin_Latn", "Lingala", "Lingála"),
    _L("lo", "lao_Laoo", "Lao", "ລາວ"),
    _L("lt", "lit_Latn", "Lithuanian", "Lietuvių"),
    _L("lmo", "lmo_Latn", "Lombard", "Lombard"),
    _L("lv", "lvs_Latn", "Latvian", "Latviešu"),
    _L("lb", "ltz_Latn", "Luxembourgish", "Lëtzebuergesch"),
    _L("mg", "plt_Latn", "Malagasy"),
    _L("mi", "mri_Latn", "Maori", "Te Reo Māori"),
    _L("mk", "mkd_Cyrl", "Macedonian", "Македонски"),
    _L("ml", "mal_Mlym", "Malayalam", "മലയാളം"),
    _L("mn", "khk_Cyrl", "Mongolian", "Монгол"),
    _L("mr", "mar_Deva", "Marathi", "मराठी"),
    _L("ms", "zsm_Latn", "Malay", "Bahasa Melayu"),
    _L("mt", "mlt_Latn", "Maltese", "Malti"),
    _L("my", "mya_Mymr", "Burmese", "မြန်မာ"),
    _L("ne", "npi_Deva", "Nepali", "नेपाली"),
    _L("nl", "nld_Latn", "Dutch", "Nederlands"),
    _L("no", "nob_Latn", "Norwegian", "Norsk bokmål"),
    _L("oc", "oci_Latn", "Occitan"),
    _L("om", "gaz_Latn", "Oromo", "Afaan Oromoo"),
    _L("pa", "pan_Guru", "Punjabi", "ਪੰਜਾਬੀ"),
    _L("pag", "pag_Latn", "Pangasinan", "Salitan Pangasinan"),
    _L("pam", "pam_Latn", "Kapampangan", "Kapampangan"),
    _L("pl", "pol_Latn", "Polish", "Polski"),
    _L("ps", "pbt_Arab", "Pashto", "پښتو", rtl=True),
    _L("pt", "por_Latn", "Portuguese", "Português"),
    _L("qu", "quy_Latn", "Quechua", "Runasimi"),
    _L("ro", "ron_Latn", "Romanian", "Română"),
    _L("ru", "rus_Cyrl", "Russian", "Русский"),
    _L("sa", "san_Deva", "Sanskrit", "संस्कृतम्"),
    _L("sd", "snd_Arab", "Sindhi", "سنڌي", rtl=True),
    _L("si", "sin_Sinh", "Sinhala", "සිංහල"),
    _L("sk", "slk_Latn", "Slovak", "Slovenčina"),
    _L("sl", "slv_Latn", "Slovenian", "Slovenščina"),
    _L("sq", "als_Latn", "Albanian", "Shqip"),
    _L("sr", "srp_Cyrl", "Serbian", "Српски"),
    _L("st", "sot_Latn", "Sesotho"),
    _L("su", "sun_Latn", "Sundanese", "Basa Sunda"),
    _L("sv", "swe_Latn", "Swedish", "Svenska"),
    _L("sw", "swh_Latn", "Swahili", "Kiswahili"),
    _L("ta", "tam_Taml", "Tamil", "தமிழ்"),
    _L("te", "tel_Telu", "Telugu", "తెలుగు"),
    _L("tg", "tgk_Cyrl", "Tajik", "Тоҷикӣ"),
    _L("th", "tha_Thai", "Thai", "ไทย"),
    _L("tl", "tgl_Latn", "Tagalog"),
    _L("tn", "tsn_Latn", "Tswana", "Setswana"),
    _L("tr", "tur_Latn", "Turkish", "Türkçe"),
    _L("tk", "tuk_Latn", "Turkmen", "Türkmen"),
    _L("ts", "tso_Latn", "Tsonga", "Xitsonga"),
    _L("tt", "tat_Cyrl", "Tatar", "Татарча"),
    _L("ug", "uig_Arab", "Uyghur", "ئۇيغۇرچە", rtl=True),
    _L("uk", "ukr_Cyrl", "Ukrainian", "Українська"),
    _L("ur", "urd_Arab", "Urdu", "اردو", rtl=True),
    _L("uz", "uzn_Latn", "Uzbek", "Oʻzbekcha"),
    _L("vi", "vie_Latn", "Vietnamese", "Tiếng Việt"),
    _L("wo", "wol_Latn", "Wolof"),
    _L("xh", "xho_Latn", "Xhosa", "isiXhosa"),
    _L("yi", "ydd_Hebr", "Yiddish", "ייִדיש", rtl=True),
    _L("yo", "yor_Latn", "Yoruba", "Yorùbá"),
    _L("zh", "zho_Hans", "Chinese (Simplified)", "简体中文"),
    _L("zh-Hant", "zho_Hant", "Chinese (Traditional)", "繁體中文"),
    _L("zu", "zul_Latn", "Zulu", "isiZulu"),
    # Codes without a single ISO 639-1 letter, or whose 639-1 code collapses
    # several of the model's distinct languages.
    _L("ckb", "ckb_Arab", "Kurdish (Sorani)", "کوردیی ناوەندی", rtl=True),
    _L("kmr", "kmr_Latn", "Kurdish (Kurmanji)", "Kurmancî"),
    _L("mai", "mai_Deva", "Maithili", "मैथिली"),
    _L("scn", "scn_Latn", "Sicilian", "Sicilianu"),
    _L("yue", "yue_Hant", "Cantonese", "廣東話"),
    _L("prs", "prs_Arab", "Dari", "دری", rtl=True),
)

#: app code -> model token
NLLB_CODES: dict[str, str] = {lang.code: lang.nllb for lang in NLLB_LANGUAGES}

#: The variants a locale-aware client may send that the model cannot
#: distinguish; they resolve to the base language instead of being advertised
#: as separate ones. DeepL has real per-variant models, NLLB has one token.
LOCALE_VARIANTS: dict[str, str] = {
    "en-US": "en", "en-GB": "en", "en-AU": "en", "en-IN": "en",
    "de-CH": "de", "fr-CA": "fr", "es-419": "es", "es-MX": "es", "es-AR": "es",
    "pt-BR": "pt", "zh-CN": "zh", "zh-TW": "zh-Hant", "zh-HK": "zh-Hant",
    "ar-EG": "ar", "ar-SA": "ar", "hi-Latn": "hi",
}

#: DeepL's own list distinguishes these regional variants; they appear in the
#: `/api/v1/languages` pickers with DeepL's display names and codes, and every
#: request for one resolves to the base code above before it reaches a model.
#: A variant row is only advertised when its base language is actually served
#: (`app/routers/translate.py`), so it can never promise work the model does
#: not do — the same show-only-what-works rule the registry enforces for
#: whole languages. The label names a locale convention, not separate weights.
PICKER_VARIANTS: tuple[tuple[str, str, str], ...] = (
    ("en-US", "en", "English (American)"),
    ("en-GB", "en", "English (British)"),
    ("de-CH", "de", "German (Switzerland)"),
    ("es-419", "es", "Spanish (Latin American)"),
    ("fr-CA", "fr", "French (Canadian)"),
    ("pt-BR", "pt", "Portuguese (Brazilian)"),
)

_BY_TOKEN = {lang.nllb: lang for lang in NLLB_LANGUAGES}
_BY_LOWER_CODE = {lang.code.lower(): lang.code for lang in NLLB_LANGUAGES}
_BY_LOWER_TOKEN = {lang.nllb.lower(): lang for lang in NLLB_LANGUAGES}


def normalize_lang(code: str | None) -> str:
    """Any spelling of a language the caller may send -> this registry's code.

    Accepts app codes, model tokens (``mar_Deva``), and BCP-47 locales
    (``pt-BR``), case- and separator-insensitively.
    """
    if not code:
        return ""
    raw = code.strip()
    if not raw or raw.lower() == "auto":
        return raw.lower()
    if raw in NLLB_CODES:
        return raw
    # A model token must come back as the registry code, not as itself: the
    # capability table is keyed by code, so `mar_Deva` returned verbatim reads
    # to the API as "language not in the registry" (422) for a language the
    # checkpoint serves.
    served = _BY_TOKEN.get(raw)
    if served is not None:
        return served.code
    variant = LOCALE_VARIANTS.get(raw)
    if variant:
        return variant
    # Case-insensitive on the WHOLE string, before the region subtag is
    # dropped: "ZH-HANT" is the Traditional Chinese row, and folding it to
    # "zh" would serve Simplified under a request for Traditional.
    by_lower_code = _BY_LOWER_CODE.get(raw.lower())
    if by_lower_code is not None:
        return by_lower_code
    by_lower_token = _BY_LOWER_TOKEN.get(raw.lower())
    if by_lower_token is not None:
        return by_lower_token.code
    # Unknown region subtag: "sw-KE" is still Swahili for a model with one
    # Swahili token. Only strip when the base is a language we serve.
    base = raw.split("-")[0]
    if base in NLLB_CODES:
        return base
    if base in _BY_TOKEN:
        return _BY_TOKEN[base].code
    return base.lower()


def nllb_code(code: str | None) -> str | None:
    """The model token for an app code / locale / token, or None if the
    checkpoint cannot serve that language."""
    resolved = normalize_lang(code)
    if not resolved or resolved == "auto":
        return None
    return NLLB_CODES.get(resolved)


def language_tokens(model_dir: str | Path) -> set[str]:
    """Every language token in this checkpoint's vocabulary.

    Read from ``special_tokens_map.json`` — no model load. The output of a
    multilingual CT2 model starts with its target-language token, so callers
    that decode raw pieces need this set to strip it.
    """
    path = Path(model_dir) / "special_tokens_map.json"
    try:
        return set(json.loads(path.read_text(encoding="utf-8"))
                   .get("additional_special_tokens") or [])
    except (OSError, ValueError):
        return set()


def checkpoint_codes(model_dir: str | Path) -> set[str]:
    """App codes whose model token is in this checkpoint's vocabulary.

    Same reason to read the file instead of the table: a checkpoint converted
    for a subset of NLLB must not advertise languages it cannot decode. Cheap
    enough to call per request, and the adapter caches the result.
    """
    tokens = language_tokens(model_dir)
    return {lang.code for lang in NLLB_LANGUAGES if lang.nllb in tokens}


def language_for_code(code: str) -> NllbLanguage | None:
    token = nllb_code(code)
    return _BY_TOKEN.get(token) if token else None

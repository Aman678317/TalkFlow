"""Constants and enumerations for Desi Language AI and GlobalTalk AI."""

from enum import Enum

DEFAULT_SERVER_URL = "https://api.globaltalk.ai"
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_RETRIES = 3

class Formality(str, Enum):
    DEFAULT = "default"
    MORE = "more"
    LESS = "less"
    PREFER_MORE = "prefer_more"
    PREFER_LESS = "prefer_less"

class IndicHonorific(str, Enum):
    FORMAL = "formal"          # Aap (आप)
    FAMILIAR = "familiar"      # Tum (तुम)
    INTIMATE = "intimate"      # Tu (तू)
    RESPECTFUL = "respectful"  # -ji / -garu / -avargal
    NEUTRAL = "neutral"

class IndicScript(str, Enum):
    LATIN = "latin"
    DEVANAGARI = "devanagari"
    BENGALI = "bengali"
    GURMUKHI = "gurmukhi"
    GUJARATI = "gujarati"
    ODIA = "odia"
    TAMIL = "tamil"
    TELUGU = "telugu"
    KANNADA = "kannada"
    MALAYALAM = "malayalam"

class WritingStyle(str, Enum):
    ACADEMIC = "academic"
    BUSINESS = "business"
    CASUAL = "casual"
    SIMPLE = "simple"
    CREATIVE = "creative"

class WritingTone(str, Enum):
    CONFIDENT = "confident"
    DIPLOMATIC = "diplomatic"
    ENTHUSIASTIC = "enthusiastic"
    FRIENDLY = "friendly"
    NEUTRAL = "neutral"

# 22 Official Eighth Schedule Indian Languages
INDIC_LANGUAGES = {
    "as": {"name": "Assamese", "native_name": "অসমীয়া", "script": "Bengali", "family": "Indo-Aryan"},
    "bn": {"name": "Bengali", "native_name": "বাংলা", "script": "Bengali", "family": "Indo-Aryan"},
    "brx": {"name": "Bodo", "native_name": "बड़ो", "script": "Devanagari", "family": "Tibeto-Burman"},
    "doi": {"name": "Dogri", "native_name": "डोगरी", "script": "Devanagari", "family": "Indo-Aryan"},
    "gu": {"name": "Gujarati", "native_name": "ગુજરાતી", "script": "Gujarati", "family": "Indo-Aryan"},
    "hi": {"name": "Hindi", "native_name": "हिन्दी", "script": "Devanagari", "family": "Indo-Aryan"},
    "kn": {"name": "Kannada", "native_name": "ಕನ್ನಡ", "script": "Kannada", "family": "Dravidian"},
    "ks": {"name": "Kashmiri", "native_name": "कॉशुर", "script": "Perso-Arabic/Devanagari", "family": "Indo-Aryan"},
    "kok": {"name": "Konkani", "native_name": "कोंकणी", "script": "Devanagari", "family": "Indo-Aryan"},
    "mai": {"name": "Maithili", "native_name": "मैथिली", "script": "Devanagari", "family": "Indo-Aryan"},
    "ml": {"name": "Malayalam", "native_name": "മലയാളം", "script": "Malayalam", "family": "Dravidian"},
    "mni": {"name": "Manipuri", "native_name": "মৈতৈলোন্", "script": "Bengali/Meetei Mayek", "family": "Tibeto-Burman"},
    "mr": {"name": "Marathi", "native_name": "मराठी", "script": "Devanagari", "family": "Indo-Aryan"},
    "ne": {"name": "Nepali", "native_name": "नेपाली", "script": "Devanagari", "family": "Indo-Aryan"},
    "or": {"name": "Odia", "native_name": "ଓଡ଼ିଆ", "script": "Odia", "family": "Indo-Aryan"},
    "pa": {"name": "Punjabi", "native_name": "ਪੰਜਾਬੀ", "script": "Gurmukhi", "family": "Indo-Aryan"},
    "sa": {"name": "Sanskrit", "native_name": "संस्कृतम्", "script": "Devanagari", "family": "Indo-Aryan"},
    "sat": {"name": "Santali", "native_name": "ᱥᱟᱱᱛᱟᱲᱤ", "script": "Ol Chiki", "family": "Austroasiatic"},
    "sd": {"name": "Sindhi", "native_name": "سنڌي", "script": "Arabic/Devanagari", "family": "Indo-Aryan"},
    "ta": {"name": "Tamil", "native_name": "தமிழ்", "script": "Tamil", "family": "Dravidian"},
    "te": {"name": "Telugu", "native_name": "తెలుగు", "script": "Telugu", "family": "Dravidian"},
    "ur": {"name": "Urdu", "native_name": "اردو", "script": "Perso-Arabic", "family": "Indo-Aryan"},
}

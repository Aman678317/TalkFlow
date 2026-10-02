"""Built-in evaluation datasets (sections 43/44/90/113).

Focus: Indian-language-first categories — names, Indian locations, numbers, currency,
code-switching (Hinglish/Marathi-English), dates, URLs, technical/legal/financial terms.
Reference translations are human-checked seeds; extend per language pair before promoting
anything to PRODUCTION. Audio golden sets (clean/noise/accent/code-switch/overlap) are
referenced by manifest — actual recordings are downloaded by ops into EVAL_AUDIO_PATH,
never committed.
"""
from __future__ import annotations

# (source, reference_target, category)
MT_EN_HI: list[tuple[str, str, str]] = [
    ("Good morning, how are you?", "सुप्रभात, आप कैसे हैं?", "greeting"),
    ("The meeting will start at ten o'clock.", "मीटिंग दस बजे शुरू होगी।", "time"),
    ("Our revenue grew by twelve percent this quarter.",
     "इस तिमाही हमारा राजस्व बारह प्रतिशत बढ़ा।", "finance"),
    ("Please sign the agreement before Friday.", "कृपया शुक्रवार से पहले समझौते पर हस्ताक्षर करें।", "legal"),
    ("The server latency is measured in milliseconds.", "सर्वर विलंबता मिलीसेकंड में मापी जाती है।", "technical"),
    ("Mumbai is the financial capital of India.", "मुंबई भारत की वित्तीय राजधानी है।", "location"),
    ("Amit Sharma will present the quarterly results.", "अमित शर्मा तिमाही परिणाम प्रस्तुत करेंगे।", "name"),
    ("The total cost is five thousand rupees.", "कुल लागत पाँच हज़ार रुपये है।", "currency"),
    ("Visit https://example.com/docs for the API reference.",
     "एपीआई संदर्भ के लिए https://example.com/docs पर जाएँ।", "url"),
    ("The date of birth is 15/08/1947.", "जन्म तिथि 15/08/1947 है।", "date"),
]

MT_HI_EN: list[tuple[str, str, str]] = [
    ("नमस्ते, आप कैसे हैं?", "Hello, how are you?", "greeting"),
    ("हमारी टीम कल नई योजना पर चर्चा करेगी।", "Our team will discuss the new plan tomorrow.", "general"),
    ("यह दस्तावेज़ कानूनी रूप से बाध्यकारी है।", "This document is legally binding.", "legal"),
    ("पाँच हज़ार रुपये जमा करें।", "Deposit five thousand rupees.", "currency"),
    ("मुंबई में बारिश हो रही है।", "It is raining in Mumbai.", "location"),
]

# code-switching (Hinglish) — STT + MT robustness
CODE_SWITCH_HI: list[tuple[str, str, str]] = [
    ("Meeting ka time change ho gaya hai, please check karo.",
     "The meeting time has changed, please check.", "hinglish"),
    ("Mera laptop hang ho raha hai, IT ko call karo.",
     "My laptop is hanging, call the IT team.", "hinglish"),
    ("Deadline next week ki hai, thoda push karna padega.",
     "The deadline is next week, we will have to push a bit.", "hinglish"),
]

MT_EN_MR: list[tuple[str, str, str]] = [
    ("Good morning, how are you?", "सदय नमस्कार, तुम्ही कसे आहात?", "greeting"),
    ("The meeting will start at ten.", "सभा दहा वाजता सुरू होईल.", "time"),
    ("Our team will discuss the new plan.", "आमचा संघ नवीन योजनेवर चर्चा करेल.", "general"),
]

# STT golden audio manifest (files provided by ops, never committed)
STT_AUDIO_MANIFEST = {
    "hi_clean_male": {"file": "hi_clean_male.wav", "language": "hi",
                      "reference": "नमस्ते, आज हम नई योजना पर चर्चा करेंगे।", "condition": "clean"},
    "hi_clean_female": {"file": "hi_clean_female.wav", "language": "hi",
                        "reference": "मीटिंग दस बजे शुरू होगी।", "condition": "clean"},
    "hi_noise": {"file": "hi_noise.wav", "language": "hi",
                 "reference": "कृपया दस्तावेज़ भेजें।", "condition": "noise"},
    "hi_code_switch": {"file": "hi_code_switch.wav", "language": "hi",
                       "reference": "Meeting ka time change ho gaya hai.", "condition": "code-switch"},
    "en_accent_indian": {"file": "en_accent_indian.wav", "language": "en",
                         "reference": "We will release the new version next quarter.",
                         "condition": "accent"},
    "mr_clean": {"file": "mr_clean.wav", "language": "mr",
                 "reference": "नमस्कार, तुम्ही कसे आहात?", "condition": "clean"},
    "overlap_two_speakers": {"file": "overlap.wav", "language": "en",
                             "reference": "", "condition": "overlap"},
}

DATASETS = {
    ("mt", "en", "hi"): MT_EN_HI,
    ("mt", "hi", "en"): MT_HI_EN,
    ("mt", "en", "mr"): MT_EN_MR,
    ("mt-codeswitch", "hi", "en"): CODE_SWITCH_HI,
}

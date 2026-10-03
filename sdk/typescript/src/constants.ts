/**
 * Constants and enumerations for Desi Language AI & GlobalTalk AI SDK.
 */

export const DEFAULT_BASE_URL = 'https://api.globaltalk.ai';
export const DEFAULT_TIMEOUT_MS = 30000;
export const DEFAULT_MAX_RETRIES = 3;

export const FormalityTier = {
  FORMAL: 'formal',
  FAMILIAR: 'familiar',
  INTIMATE: 'intimate',
  RESPECTFUL: 'respectful',
  NEUTRAL: 'neutral',
} as const;

export type FormalityTierType = typeof FormalityTier[keyof typeof FormalityTier];

export const IndicScript = {
  LATIN: 'latin',
  DEVANAGARI: 'devanagari',
  BENGALI: 'bengali',
  GURMUKHI: 'gurmukhi',
  GUJARATI: 'gujarati',
  ODIA: 'odia',
  TAMIL: 'tamil',
  TELUGU: 'telugu',
  KANNADA: 'kannada',
  MALAYALAM: 'malayalam',
} as const;

export type IndicScriptType = typeof IndicScript[keyof typeof IndicScript];

export const INDIC_LANGUAGES: Record<string, { name: string; nativeName: string; script: string }> = {
  as: { name: 'Assamese', nativeName: 'অসমীয়া', script: 'Bengali' },
  bn: { name: 'Bengali', nativeName: 'বাংলা', script: 'Bengali' },
  brx: { name: 'Bodo', nativeName: 'बड़ो', script: 'Devanagari' },
  doi: { name: 'Dogri', nativeName: 'डोगरी', script: 'Devanagari' },
  gu: { name: 'Gujarati', nativeName: 'ગુજરાતી', script: 'Gujarati' },
  hi: { name: 'Hindi', nativeName: 'हिन्दी', script: 'Devanagari' },
  kn: { name: 'Kannada', nativeName: 'ಕನ್ನಡ', script: 'Kannada' },
  ks: { name: 'Kashmiri', nativeName: 'कॉशुर', script: 'Perso-Arabic' },
  kok: { name: 'Konkani', nativeName: 'कोंकणी', script: 'Devanagari' },
  mai: { name: 'Maithili', nativeName: 'मैथिली', script: 'Devanagari' },
  ml: { name: 'Malayalam', nativeName: 'മലയാളം', script: 'Malayalam' },
  mni: { name: 'Manipuri', nativeName: 'মৈতৈলোন্', script: 'Bengali' },
  mr: { name: 'Marathi', nativeName: 'मराठी', script: 'Devanagari' },
  ne: { name: 'Nepali', nativeName: 'नेपाली', script: 'Devanagari' },
  or: { name: 'Odia', nativeName: 'ଓଡ଼ିଆ', script: 'Odia' },
  pa: { name: 'Punjabi', nativeName: 'ਪੰਜਾਬੀ', script: 'Gurmukhi' },
  sa: { name: 'Sanskrit', nativeName: 'संस्कृतम्', script: 'Devanagari' },
  sat: { name: 'Santali', nativeName: 'ᱥᱟᱱᱛᱟᱲᱤ', script: 'Ol Chiki' },
  sd: { name: 'Sindhi', nativeName: 'سنڌي', script: 'Arabic' },
  ta: { name: 'Tamil', nativeName: 'தமிழ்', script: 'Tamil' },
  te: { name: 'Telugu', nativeName: 'తెలుగు', script: 'Telugu' },
  ur: { name: 'Urdu', nativeName: 'اردو', script: 'Perso-Arabic' },
};

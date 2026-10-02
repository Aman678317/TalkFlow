// Application constants for Amazon Connect Desi V2V
export const DEPRECATED_CONNECT_DOMAIN = "awsapps.com";

export const SESSION_STORAGE_KEYS = {};

export const LOGGER_PREFIX = "CCP-DESI-V2V";

export const CUSTOMER_TRANSLATION_TO_CUSTOMER_VOLUME = 0.15;
export const AGENT_TRANSLATION_TO_AGENT_VOLUME = 0.15;

export const TRANSCRIBE_PARTIAL_RESULTS_STABILITY = ["low", "medium", "high"];

export const AUDIO_FEEDBACK_FILE_PATH = "./assets/background_noise.wav";

// Audio & DSP constants
export const SYNTH_DUCK_GAIN = 0.1;     // Gain applied to synthesized speech during speaker barge-in
export const VAD_HOLD_TIME_MS = 500;    // Duration after VAD drops before unducking playback
export const AUDIO_INGEST_SAMPLE_RATE = 16000;
export const AUDIO_OUTPUT_SAMPLE_RATE = 16000;
export const BUFFER_LEN = 3200;         // 200ms frame at 16kHz mono 16-bit

// Formality & Indic AI constants
export const DESI_FORMALITY_TIERS = [
  { value: "formal", label: "Formal (आप / Aap) - Respectful" },
  { value: "familiar", label: "Familiar (तुम / Tum) - Peers/Colleagues" },
  { value: "intimate", label: "Intimate (तू / Tu) - Family/Close Friends" },
  { value: "respectful", label: "Respectful Suffix (-जी / -garu / -avargal)" },
  { value: "default", label: "Default Formality" }
];

// Latency evaluation constants
export const LATENCY_TRACKING_ENABLED = true;
export const VAD_RMS_MIN_THRESHOLD = 0.04;
export const PIPELINE_LATENCY_MAX_MS_GOOD = 1500;
export const PIPELINE_LATENCY_MAX_MS_OK = 2500;
export const TURN_LATENCY_MAX_MS_GOOD = 4000;
export const TURN_LATENCY_MAX_MS_OK = 8000;

// Health monitoring constants
export const HEALTH_CHECK_INTERVAL_MS = 1000;
export const DEGRADED_THRESHOLD_MS = 3000;
export const POOR_THRESHOLD_MS = 5000;

export const ZOMBIE_DETECTION_TIMEOUT_SPEAKING_MS = 30000;
export const ZOMBIE_DETECTION_TIMEOUT_SILENT_MS = 60000;
export const SPEECH_GRACE_PERIOD_MS = 20000;

export const MAX_RECONNECT_ATTEMPTS = 5;
export const INITIAL_BACKOFF_MS = 1000;
export const MAX_BACKOFF_MS = 30000;

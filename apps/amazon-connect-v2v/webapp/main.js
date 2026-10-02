// Amazon Connect + Desi Voice-to-Voice (V2V) Main Orchestrator
import "amazon-connect-streams";
import { CONNECT_CONFIG } from "./config";
import { LOGGER_PREFIX } from "./constants";
import { SUPPORTED_SOURCE_LANGUAGES, SUPPORTED_TARGET_LANGUAGES } from "./supportedLanguages";
import { AudioContextManager } from "./managers/AudioContextManager";
import { AudioStreamManager } from "./managers/AudioStreamManager";
import { SessionTrackManager } from "./managers/SessionTrackManager";
import { AudioLatencyTrackManager } from "./managers/AudioLatencyTrackManager";
import { DesiVoiceClient } from "./adapters/desiVoiceAdapter";
import { handleAuthRedirect } from "./utils/authUtility";

// Initialize Authentication Redirect
handleAuthRedirect();

// State
let toCustomerAudioStreamManager = null;
let toAgentAudioStreamManager = null;
let sessionTrackManager = null;
let latencyTrackManager = null;

let agentVoiceClient = null;
let customerVoiceClient = null;
let activeMicStream = null;
let activeCallMediaStream = null;

// DOM Elements
const customerLangSelect = document.getElementById("customerLanguageSelect");
const customerFormalitySelect = document.getElementById("customerFormalitySelect");
const customerVoiceIdSelect = document.getElementById("customerVoiceIdSelect");
const customerTtsProviderSelect = document.getElementById("customerTtsProviderSelect");
const customerTransDiv = document.getElementById("customerTranscriptionTextOutputDiv");
const customerTransResultDiv = document.getElementById("customerTranslatedTextOutputDiv");
const customerVadIndicator = document.getElementById("customerVadIndicator");

const agentLangSelect = document.getElementById("agentLanguageSelect");
const agentFormalitySelect = document.getElementById("agentFormalitySelect");
const agentVoiceIdSelect = document.getElementById("agentVoiceIdSelect");
const agentTtsProviderSelect = document.getElementById("agentTtsProviderSelect");
const agentTransDiv = document.getElementById("agentTranscriptionTextOutputDiv");
const agentTransResultDiv = document.getElementById("agentTranslatedTextOutputDiv");
const agentVadIndicator = document.getElementById("agentVadIndicator");

const transcriptContainer = document.getElementById("divTranscriptContainer");
const muteAgentBtn = document.getElementById("agentMuteTranscriptionButton");
const envSelect = document.getElementById("environmentSelect");

// --------------------------------------------------------------------------- //
// Initialization
// --------------------------------------------------------------------------- //

async function initApp() {
  console.log(`${LOGGER_PREFIX} - Initializing Desi Voice-to-Voice Application`);

  // 1. Audio Managers
  toCustomerAudioStreamManager = new AudioStreamManager("ToCustomerAudioStreamManager");
  toAgentAudioStreamManager = new AudioStreamManager("ToAgentAudioStreamManager");
  sessionTrackManager = new SessionTrackManager(toCustomerAudioStreamManager);
  latencyTrackManager = new AudioLatencyTrackManager();

  // Attach audio elements
  const toCustomerEl = document.getElementById("toCustomerAudioElement");
  const toAgentEl = document.getElementById("toAgentAudioElement");
  if (toCustomerEl) toCustomerAudioStreamManager.attachToAudioElement(toCustomerEl);
  if (toAgentEl) toAgentAudioStreamManager.attachToAudioElement(toAgentEl);

  // 2. Populate Languages
  populateLanguages();

  // 3. User Gesture / AudioContext Unlock
  window.addEventListener("click", () => AudioContextManager.resumeIfSuspended(), { once: true });

  // 4. Request Agent Microphone
  try {
    activeMicStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        sampleRate: 16000
      }
    });
    console.log(`${LOGGER_PREFIX} - Microphone captured successfully`);
  } catch (err) {
    console.error(`${LOGGER_PREFIX} - Error requesting microphone:`, err);
  }

  // 5. Initialize Amazon Connect Streams CCP
  initAmazonConnectCCP();

  // 6. Setup UI Event Listeners
  setupEventListeners();
}

function populateLanguages() {
  // Populate Customer & Agent dropdowns
  SUPPORTED_SOURCE_LANGUAGES.forEach(lang => {
    const optCust = document.createElement("option");
    optCust.value = lang.language;
    optCust.textContent = lang.name;
    if (lang.language === "hi") optCust.selected = true;
    customerLangSelect.appendChild(optCust);

    const optAgent = document.createElement("option");
    optAgent.value = lang.language;
    optAgent.textContent = lang.name;
    if (lang.language === "en") optAgent.selected = true;
    agentLangSelect.appendChild(optAgent);
  });
}

function initAmazonConnectCCP() {
  const ccpContainer = document.getElementById("ccpContainer");
  if (!ccpContainer) return;

  const instanceURL = CONNECT_CONFIG.connectInstanceURL || "https://my-connect-instance.my.connect.aws";
  console.log(`${LOGGER_PREFIX} - Initializing Connect CCP at:`, instanceURL);

  try {
    connect.core.initCCP(ccpContainer, {
      ccpUrl: `${instanceURL}/connect/ccp-v2/`,
      loginPopup: true,
      loginPopupAutoClose: true,
      softphone: {
        allowFramedSoftphone: true,
        disableRingtone: false
      }
    });

    connect.contact(onContactHandler);
  } catch (e) {
    console.warn(`${LOGGER_PREFIX} - Connect CCP initialization bypassed or running offline:`, e);
  }
}

function onContactHandler(contact) {
  sessionTrackManager.setContact(contact);

  contact.onConnecting(() => {
    console.log(`${LOGGER_PREFIX} - Call incoming / connecting...`);
  });

  contact.onConnected(async () => {
    console.log(`${LOGGER_PREFIX} - Call Connected! Activating Desi V2V Pipelines.`);
    await AudioContextManager.resumeIfSuspended();

    // In a live Amazon Connect call, remote audio is delivered via connect.core softphone manager
    // or WebRTC media stream.
    startDesiPipelines();
  });

  contact.onEnded(() => {
    console.log(`${LOGGER_PREFIX} - Call Ended. Halting Desi V2V Pipelines.`);
    stopDesiPipelines();
  });
}

function startDesiPipelines() {
  const custLang = customerLangSelect.value || "hi";
  const agentLang = agentLangSelect.value || "en";
  const custFormality = customerFormalitySelect.value || "formal";
  const env = envSelect.value || "prod";

  // 1. Agent -> Customer Pipeline
  if (activeMicStream) {
    agentVoiceClient = new DesiVoiceClient({
      name: "AgentVoiceClient",
      participant: "agent",
      sourceLanguage: agentLang,
      targetLanguage: custLang,
      formality: custFormality,
      voice: agentVoiceIdSelect.value || "female",
      environment: env,
      audioStreamManager: toCustomerAudioStreamManager,
      latencyTrackManager: latencyTrackManager,
      onTranscription: (text, isFinal) => {
        agentTransDiv.textContent = text;
        if (isFinal) addTranscriptCard("agent", text, agentTransResultDiv.textContent);
      },
      onTranslation: (translatedText, sourceText) => {
        agentTransResultDiv.textContent = translatedText;
        updateLastTranscriptCard("agent", sourceText, translatedText);
      },
      onVadChanged: (speaking) => {
        agentVadIndicator.classList.toggle("speaking", speaking);
        if (speaking && document.getElementById("agentInterruptOnSpeakCheckbox")?.checked) {
          toAgentAudioStreamManager.duck();
        } else {
          toAgentAudioStreamManager.unduck();
        }
      }
    });

    agentVoiceClient.start(activeMicStream);
  }

  // 2. Customer -> Agent Pipeline
  // For demo/browser testing, if no external phone audio is connected, customer can be simulated
  const remoteEl = document.getElementById("remote-audio");
  const remoteStream = remoteEl?.srcObject || activeMicStream;

  if (remoteStream) {
    customerVoiceClient = new DesiVoiceClient({
      name: "CustomerVoiceClient",
      participant: "customer",
      sourceLanguage: custLang,
      targetLanguage: agentLang,
      formality: "default",
      voice: customerVoiceIdSelect.value || "female",
      environment: env,
      audioStreamManager: toAgentAudioStreamManager,
      latencyTrackManager: latencyTrackManager,
      onTranscription: (text, isFinal) => {
        customerTransDiv.textContent = text;
        if (isFinal) addTranscriptCard("customer", text, customerTransResultDiv.textContent);
      },
      onTranslation: (translatedText, sourceText) => {
        customerTransResultDiv.textContent = translatedText;
        updateLastTranscriptCard("customer", sourceText, translatedText);
      },
      onVadChanged: (speaking) => {
        customerVadIndicator.classList.toggle("speaking", speaking);
        if (speaking && document.getElementById("customerInterruptOnSpeakCheckbox")?.checked) {
          toCustomerAudioStreamManager.duck();
        } else {
          toCustomerAudioStreamManager.unduck();
        }
      }
    });

    customerVoiceClient.start(remoteStream);
  }

  // Replace Connect outbound sender track with translated audio
  sessionTrackManager.replaceOutgoingTrack();
}

function stopDesiPipelines() {
  if (agentVoiceClient) {
    agentVoiceClient.stop();
    agentVoiceClient = null;
  }
  if (customerVoiceClient) {
    customerVoiceClient.stop();
    customerVoiceClient = null;
  }
  toCustomerAudioStreamManager?.stopAllPlayback();
  toAgentAudioStreamManager?.stopAllPlayback();
}

function addTranscriptCard(speaker, originalText, translatedText = "") {
  const card = document.createElement("div");
  card.className = `transcript-card ${speaker === "agent" ? "fromAgent" : "toAgent"}`;

  const origDiv = document.createElement("div");
  origDiv.className = "transcript-original";
  origDiv.textContent = `${speaker === "agent" ? "Agent" : "Customer"}: ${originalText}`;

  const sep = document.createElement("div");
  sep.className = "transcript-separator";

  const transDiv = document.createElement("div");
  transDiv.className = "transcript-translated";
  transDiv.textContent = translatedText ? `Translated: ${translatedText}` : "...translating";

  card.appendChild(origDiv);
  card.appendChild(sep);
  card.appendChild(transDiv);
  transcriptContainer.appendChild(card);
  transcriptContainer.scrollTop = transcriptContainer.scrollHeight;
}

function updateLastTranscriptCard(speaker, originalText, translatedText) {
  const cards = transcriptContainer.querySelectorAll(`.${speaker === "agent" ? "fromAgent" : "toAgent"}`);
  if (cards.length === 0) return;
  const lastCard = cards[cards.length - 1];
  const transEl = lastCard.querySelector(".transcript-translated");
  if (transEl) {
    transEl.textContent = `Translated: ${translatedText}`;
  }
}

function setupEventListeners() {
  muteAgentBtn?.addEventListener("click", () => {
    if (!agentVoiceClient) return;
    agentVoiceClient.isMuted = !agentVoiceClient.isMuted;
    muteAgentBtn.textContent = agentVoiceClient.isMuted ? "Unmute Translation" : "Mute Translation";
    muteAgentBtn.classList.toggle("muted", agentVoiceClient.isMuted);
  });

  customerLangSelect?.addEventListener("change", () => {
    if (customerVoiceClient) {
      stopDesiPipelines();
      startDesiPipelines();
    }
  });

  agentLangSelect?.addEventListener("change", () => {
    if (agentVoiceClient) {
      stopDesiPipelines();
      startDesiPipelines();
    }
  });

  customerFormalitySelect?.addEventListener("change", () => {
    if (agentVoiceClient) {
      agentVoiceClient.formality = customerFormalitySelect.value;
    }
  });
}

// Start App on DOM Ready
window.addEventListener("DOMContentLoaded", initApp);

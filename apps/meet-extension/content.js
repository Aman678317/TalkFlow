/* TalkFlow Google Meet Real-Time Translation Content Script */

(() => {
  let isRunning = false;
  let overlayContainer = null;
  let originalCaptionText = "";
  let lastTranslatedText = "";
  let translationDebounceTimer = null;
  let audioContext = null;

  const API_BASE = "http://127.0.0.1:8000";

  function createOverlay() {
    if (document.getElementById("talkflow-meet-overlay")) return;

    overlayContainer = document.createElement("div");
    overlayContainer.id = "talkflow-meet-overlay";
    overlayContainer.innerHTML = `
      <div class="tf-card">
        <div class="tf-header">
          <div class="tf-indicator">
            <span class="tf-dot"></span>
            <span class="tf-title">TalkFlow Live Translation</span>
          </div>
          <div class="tf-lang-badge" id="tfLangBadge">Auto &rarr; EN</div>
        </div>
        <div class="tf-body">
          <div class="tf-translated" id="tfTranslated">Listening for meeting speech...</div>
          <div class="tf-original" id="tfOriginal">Google Meet live translation active</div>
        </div>
      </div>
    `;
    document.body.appendChild(overlayContainer);
  }

  function removeOverlay() {
    const el = document.getElementById("talkflow-meet-overlay");
    if (el) el.remove();
    overlayContainer = null;
  }

  function updateSubtitles(original, translated, srcLang, tgtLang) {
    if (!overlayContainer) createOverlay();
    const transEl = document.getElementById("tfTranslated");
    const origEl = document.getElementById("tfOriginal");
    const badgeEl = document.getElementById("tfLangBadge");

    if (transEl && translated) transEl.textContent = translated;
    if (origEl && original) origEl.textContent = original;
    if (badgeEl) badgeEl.textContent = `${srcLang.toUpperCase()} → ${tgtLang.toUpperCase()}`;
  }

  async function translateText(text, src, tgt, playVoice) {
    if (!text || text === lastTranslatedText) return;
    lastTranslatedText = text;

    try {
      const res = await fetch(`${API_BASE}/api/v1/translate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text,
          source_lang: src,
          target_lang: tgt,
        }),
      });

      if (!res.ok) return;
      const data = await res.json();
      const translated = data.translated_text || data.text;
      const detectedSrc = data.detected_source_lang || src;

      updateSubtitles(text, translated, detectedSrc, tgt);

      if (playVoice && translated) {
        playNeuralVoice(translated, tgt);
      }
    } catch (e) {
      console.debug("[TalkFlow] Translation request failed:", e);
    }
  }

  function playNeuralVoice(text, lang) {
    if ("speechSynthesis" in window) {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = lang;
      utterance.rate = 1.05;
      utterance.volume = 0.95;
      window.speechSynthesis.speak(utterance);
    }
  }

  function observeGoogleMeetCaptions(settings) {
    // Observe Google Meet's native caption container or speech output
    const observer = new MutationObserver(() => {
      // Common selector patterns for Google Meet live captions
      const captionNodes = document.querySelectorAll(
        "div[jsname='YSvyTc'], div[aria-live='polite'], .bh44bd, .T4LgNb"
      );

      let fullText = "";
      captionNodes.forEach((node) => {
        const text = node.innerText.trim();
        if (text && text.length > fullText.length) {
          fullText = text;
        }
      });

      if (fullText && fullText !== originalCaptionText) {
        originalCaptionText = fullText;
        clearTimeout(translationDebounceTimer);
        translationDebounceTimer = setTimeout(() => {
          translateText(
            fullText,
            settings.speakLang || "auto",
            settings.hearLang || "en",
            settings.voiceInterpretation
          );
        }, 250);
      }
    });

    observer.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
    });

    return observer;
  }

  let meetObserver = null;

  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "START_TRANSLATION") {
      isRunning = true;
      createOverlay();
      if (meetObserver) meetObserver.disconnect();
      meetObserver = observeGoogleMeetCaptions(request.settings);
      sendResponse({ status: "started" });
    } else if (request.action === "STOP_TRANSLATION") {
      isRunning = false;
      if (meetObserver) {
        meetObserver.disconnect();
        meetObserver = null;
      }
      removeOverlay();
      sendResponse({ status: "stopped" });
    }
  });

  // Check state on load
  chrome.storage.local.get(["isActive", "speakLang", "hearLang", "voiceInterpretation"], (data) => {
    if (data.isActive) {
      isRunning = true;
      createOverlay();
      meetObserver = observeGoogleMeetCaptions(data);
    }
  });
})();

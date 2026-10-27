document.addEventListener("DOMContentLoaded", async () => {
  const speakLang = document.getElementById("speakLang");
  const hearLang = document.getElementById("hearLang");
  const captionStyle = document.getElementById("captionStyle");
  const voiceInterpretation = document.getElementById("voiceInterpretation");
  const toggleBtn = document.getElementById("toggleBtn");
  const statusBadge = document.getElementById("statusBadge");

  // Load saved preferences
  chrome.storage.local.get(["speakLang", "hearLang", "captionStyle", "voiceInterpretation", "isActive"], (data) => {
    if (data.speakLang) speakLang.value = data.speakLang;
    if (data.hearLang) hearLang.value = data.hearLang;
    if (data.captionStyle) captionStyle.value = data.captionStyle;
    if (data.voiceInterpretation !== undefined) voiceInterpretation.checked = data.voiceInterpretation;

    if (data.isActive) {
      toggleBtn.textContent = "Stop Live Translation";
      toggleBtn.classList.add("active");
      statusBadge.textContent = "Live";
      statusBadge.style.background = "rgba(16, 185, 129, 0.3)";
      statusBadge.style.color = "#10b981";
    }
  });

  toggleBtn.addEventListener("click", async () => {
    chrome.storage.local.get(["isActive"], async (data) => {
      const nextState = !data.isActive;
      const settings = {
        speakLang: speakLang.value,
        hearLang: hearLang.value,
        captionStyle: captionStyle.value,
        voiceInterpretation: voiceInterpretation.checked,
        isActive: nextState,
      };

      await chrome.storage.local.set(settings);

      if (nextState) {
        toggleBtn.textContent = "Stop Live Translation";
        toggleBtn.classList.add("active");
        statusBadge.textContent = "Live";
        statusBadge.style.background = "rgba(16, 185, 129, 0.3)";
        statusBadge.style.color = "#10b981";
      } else {
        toggleBtn.textContent = "Start Live Translation";
        toggleBtn.classList.remove("active");
        statusBadge.textContent = "Stopped";
        statusBadge.style.background = "rgba(148, 163, 184, 0.2)";
        statusBadge.style.color = "#94a3b8";
      }

      // Send command to content script in current tab
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (tab?.id) {
        chrome.tabs.sendMessage(tab.id, {
          action: nextState ? "START_TRANSLATION" : "STOP_TRANSLATION",
          settings,
        });
      }
    });
  });
});

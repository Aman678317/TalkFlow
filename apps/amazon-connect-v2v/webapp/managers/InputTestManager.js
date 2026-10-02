// InputTestManager - Analyzes mic input levels for the UI volume meter
import { AudioContextManager } from "./AudioContextManager";

export class InputTestManager {
  constructor(volumeBarId) {
    this.volumeBar = document.getElementById(volumeBarId);
    this.analyser = null;
    this.mediaStreamSource = null;
    this.animationId = null;
  }

  startTesting(mediaStream) {
    this.stopTesting();
    const ctx = AudioContextManager.getAudioContext();
    this.analyser = ctx.createAnalyser();
    this.analyser.fftSize = 256;
    this.mediaStreamSource = ctx.createMediaStreamSource(mediaStream);
    this.mediaStreamSource.connect(this.analyser);

    const dataArray = new Uint8Array(this.analyser.frequencyBinCount);
    const update = () => {
      this.analyser.getByteFrequencyData(dataArray);
      let sum = 0;
      for (let i = 0; i < dataArray.length; i++) {
        sum += dataArray[i];
      }
      const avg = sum / dataArray.length;
      const percent = Math.min(100, Math.round((avg / 128) * 100));

      if (this.volumeBar) {
        this.volumeBar.style.width = `${percent}%`;
      }
      this.animationId = requestAnimationFrame(update);
    };
    update();
  }

  stopTesting() {
    if (this.animationId) {
      cancelAnimationFrame(this.animationId);
      this.animationId = null;
    }
    if (this.mediaStreamSource) {
      this.mediaStreamSource.disconnect();
      this.mediaStreamSource = null;
    }
    if (this.volumeBar) {
      this.volumeBar.style.width = "0%";
    }
  }
}

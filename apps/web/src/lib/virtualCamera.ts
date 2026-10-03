/**
 * Virtual Studio Camera Generator
 * Provides an animated 1280x720 MediaStream fallback when physical webcam
 * permission is denied (e.g., in automated browser test environments,
 * headless instances, or when webcam access is blocked in site settings).
 */

export interface VirtualCameraHandle {
  stream: MediaStream;
  stop: () => void;
}

export function createVirtualCameraStream(displayName: string): VirtualCameraHandle {
  const canvas = document.createElement('canvas');
  canvas.width = 1280;
  canvas.height = 720;

  const ctx = canvas.getContext('2d');
  if (!ctx) {
    // Fallback if canvas 2D context is unavailable
    const dummy = document.createElement('canvas');
    dummy.width = 640;
    dummy.height = 360;
    const stream = (dummy as any).captureStream ? (dummy as any).captureStream(10) : new MediaStream();
    return { stream, stop: () => {} };
  }

  let animationFrameId: number;
  let t = 0;
  const initial = (displayName || 'U').trim().charAt(0).toUpperCase();
  const safeName = displayName || 'Participant';

  const render = () => {
    t += 0.03;
    const { width, height } = canvas;

    // 1. Cinematic Background Radial Gradient
    const bgGrad = ctx.createRadialGradient(
      width / 2,
      height / 2,
      60,
      width / 2,
      height / 2,
      width * 0.75
    );
    bgGrad.addColorStop(0, '#1a2234');
    bgGrad.addColorStop(0.55, '#0d1524');
    bgGrad.addColorStop(1, '#050912');
    ctx.fillStyle = bgGrad;
    ctx.fillRect(0, 0, width, height);

    // 2. Subtle Geometric Grid Pattern
    ctx.save();
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.025)';
    ctx.lineWidth = 1;
    const gridSize = 40;
    for (let x = 0; x < width; x += gridSize) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.stroke();
    }
    for (let y = 0; y < height; y += gridSize) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }
    ctx.restore();

    // 3. Ambient Pulsing Halo Waves
    const wave1 = 175 + Math.sin(t * 1.5) * 16;
    const wave2 = 230 + Math.cos(t * 1.2) * 20;
    const wave3 = 290 + Math.sin(t * 0.8) * 24;

    ctx.save();
    ctx.lineWidth = 2;
    ctx.strokeStyle = 'rgba(14, 165, 233, 0.22)'; // Cyan/Sky
    ctx.beginPath();
    ctx.arc(width / 2, height / 2, wave1, 0, Math.PI * 2);
    ctx.stroke();

    ctx.lineWidth = 1.5;
    ctx.strokeStyle = 'rgba(99, 102, 241, 0.16)'; // Indigo
    ctx.beginPath();
    ctx.arc(width / 2, height / 2, wave2, 0, Math.PI * 2);
    ctx.stroke();

    ctx.lineWidth = 1;
    ctx.strokeStyle = 'rgba(56, 189, 248, 0.10)';
    ctx.beginPath();
    ctx.arc(width / 2, height / 2, wave3, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();

    // 4. Orbiting Light Sparkle
    const orbitRadius = wave1;
    const orbitAngle = t * 1.8;
    const orbitX = width / 2 + Math.cos(orbitAngle) * orbitRadius;
    const orbitY = height / 2 + Math.sin(orbitAngle) * orbitRadius;

    ctx.save();
    ctx.fillStyle = '#38bdf8';
    ctx.shadowColor = '#38bdf8';
    ctx.shadowBlur = 14;
    ctx.beginPath();
    ctx.arc(orbitX, orbitY, 4, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();

    // 5. Central Avatar Circle
    const avatarRadius = 90;
    const avatarGrad = ctx.createLinearGradient(
      width / 2 - avatarRadius,
      height / 2 - avatarRadius,
      width / 2 + avatarRadius,
      height / 2 + avatarRadius
    );
    avatarGrad.addColorStop(0, '#0284c7'); // sky-600
    avatarGrad.addColorStop(0.5, '#2563eb'); // blue-600
    avatarGrad.addColorStop(1, '#4f46e5'); // indigo-600

    ctx.save();
    ctx.shadowColor = 'rgba(2, 132, 199, 0.45)';
    ctx.shadowBlur = 32;
    ctx.fillStyle = avatarGrad;
    ctx.beginPath();
    ctx.arc(width / 2, height / 2, avatarRadius, 0, Math.PI * 2);
    ctx.fill();

    // Avatar Inner Border Ring
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.25)';
    ctx.lineWidth = 3;
    ctx.stroke();
    ctx.restore();

    // 6. Monogram Initial Letter
    ctx.save();
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 88px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.shadowColor = 'rgba(0, 0, 0, 0.35)';
    ctx.shadowBlur = 10;
    ctx.fillText(initial, width / 2, height / 2 + 4);
    ctx.restore();

    // 7. Participant Name Pill
    ctx.save();
    ctx.font = '600 24px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    const textMetrics = ctx.measureText(safeName);
    const pillW = Math.max(textMetrics.width + 56, 200);
    const pillH = 46;
    const pillX = width / 2 - pillW / 2;
    const pillY = height / 2 + 124;

    // Dark glass pill background
    ctx.fillStyle = 'rgba(15, 23, 42, 0.88)';
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.16)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    if (typeof (ctx as any).roundRect === 'function') {
      (ctx as any).roundRect(pillX, pillY, pillW, pillH, 23);
    } else {
      ctx.rect(pillX, pillY, pillW, pillH);
    }
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = '#f8fafc';
    ctx.fillText(safeName, width / 2, pillY + pillH / 2);
    ctx.restore();

    // 8. Top-Left "Virtual Studio Camera" Tag
    ctx.save();
    const tagText = 'VIRTUAL STUDIO CAMERA';
    ctx.font = '700 13px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
    const tagW = ctx.measureText(tagText).width + 42;
    const tagH = 34;

    ctx.fillStyle = 'rgba(15, 23, 42, 0.82)';
    ctx.strokeStyle = 'rgba(56, 189, 248, 0.4)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    if (typeof (ctx as any).roundRect === 'function') {
      (ctx as any).roundRect(30, 30, tagW, tagH, 10);
    } else {
      ctx.rect(30, 30, tagW, tagH);
    }
    ctx.fill();
    ctx.stroke();

    // Blinking Live Dot
    const dotAlpha = 0.5 + 0.5 * Math.sin(t * 4);
    ctx.fillStyle = `rgba(56, 189, 248, ${dotAlpha})`;
    ctx.shadowColor = '#38bdf8';
    ctx.shadowBlur = 8;
    ctx.beginPath();
    ctx.arc(48, 47, 4.5, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = '#e0f2fe';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    ctx.shadowBlur = 0;
    ctx.fillText(tagText, 60, 48);
    ctx.restore();

    animationFrameId = requestAnimationFrame(render);
  };

  // Render first frame immediately
  render();

  const stream: MediaStream = (canvas as any).captureStream
    ? (canvas as any).captureStream(30)
    : new MediaStream();

  let isStopped = false;
  const stop = () => {
    if (isStopped) return;
    isStopped = true;
    cancelAnimationFrame(animationFrameId);
    stream.getTracks().forEach((track) => track.stop());
  };

  // Attach stop hook to the video track
  stream.getVideoTracks().forEach((track) => {
    const origStop = track.stop.bind(track);
    track.stop = () => {
      stop();
      origStop();
    };
  });

  return { stream, stop };
}

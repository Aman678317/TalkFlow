"""Media processing, video audio extraction, metadata probing, and FFmpeg remuxing engine."""
from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple
import av

logger = logging.getLogger("talkflow.orchestrator.media")

# Locate FFmpeg binary
FFMPEG_PATH = Path("I:/vioces agent/.venv/Scripts/ffmpeg.exe")
if not FFMPEG_PATH.exists():
    # Fallback to PATH or imageio_ffmpeg
    try:
        import imageio_ffmpeg
        FFMPEG_PATH = Path(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        FFMPEG_PATH = Path("ffmpeg")


class MediaProcessor:
    """Enterprise audio and video processor using FFmpeg and PyAV."""

    @staticmethod
    def compute_sha256(file_path: Path) -> str:
        """Compute SHA-256 checksum of an uploaded media file."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    def probe_media(file_path: Path) -> Dict[str, Any]:
        """Inspect media file and return duration, container, video/audio stream properties."""
        meta: Dict[str, Any] = {
            "file_name": file_path.name,
            "file_size_bytes": file_path.stat().st_size,
            "has_video": False,
            "has_audio": False,
            "duration_sec": 0.0,
            "duration_ms": 0,
            "format_name": "",
            "audio_streams": [],
            "video_streams": []
        }

        try:
            with av.open(str(file_path)) as container:
                meta["format_name"] = container.format.name or ""
                if container.duration:
                    meta["duration_sec"] = float(container.duration) / av.time_base
                    meta["duration_ms"] = int(meta["duration_sec"] * 1000)

                for s in container.streams.video:
                    meta["has_video"] = True
                    meta["video_streams"].append({
                        "codec": s.codec_context.name,
                        "width": s.codec_context.width,
                        "height": s.codec_context.height,
                        "fps": float(s.average_rate) if s.average_rate else 30.0,
                        "bit_rate": s.codec_context.bit_rate or 0
                    })

                for s in container.streams.audio:
                    meta["has_audio"] = True
                    meta["audio_streams"].append({
                        "codec": s.codec_context.name,
                        "sample_rate": s.codec_context.sample_rate,
                        "channels": s.codec_context.channels,
                        "bit_rate": s.codec_context.bit_rate or 0
                    })
        except Exception as e:
            logger.warning(f"PyAV probe failed for {file_path}: {e}. Falling back to FFmpeg probe.")
            meta = MediaProcessor._probe_with_ffmpeg(file_path, meta)

        return meta

    @staticmethod
    def _probe_with_ffmpeg(file_path: Path, base_meta: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback probe using ffmpeg command line."""
        cmd = [
            str(FFMPEG_PATH),
            "-i", str(file_path),
            "-f", "null", "-"
        ]
        try:
            res = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, timeout=10)
            output = res.stderr
            # Look for Duration: 00:04:18.30
            import re
            dur_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", output)
            if dur_match:
                h, m, s = dur_match.groups()
                dur_sec = int(h) * 3600 + int(m) * 60 + float(s)
                base_meta["duration_sec"] = dur_sec
                base_meta["duration_ms"] = int(dur_sec * 1000)
            if "Video:" in output:
                base_meta["has_video"] = True
            if "Audio:" in output:
                base_meta["has_audio"] = True
        except Exception as err:
            logger.error(f"FFmpeg fallback probe failed: {err}")
        return base_meta

    @staticmethod
    def extract_canonical_audio(
        input_file: Path,
        output_wav: Path,
        target_sample_rate: int = 16000
    ) -> Path:
        """Extract complete audio stream from video or transcode any audio to 16kHz mono PCM16 WAV.
        
        Never trims or drops any speech.
        """
        output_wav.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            str(FFMPEG_PATH),
            "-y",
            "-i", str(input_file),
            "-vn",                       # Strip video
            "-acodec", "pcm_s16le",      # 16-bit PCM
            "-ac", "1",                  # Mono
            "-ar", str(target_sample_rate), # 16000 Hz canonical
            str(output_wav)
        ]
        logger.info(f"Extracting canonical audio: {' '.join(cmd)}")
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=180)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg audio extraction failed (code {res.returncode}): {res.stderr}")

        if not output_wav.exists() or output_wav.stat().st_size == 0:
            raise RuntimeError(f"Extracted audio file is missing or 0 bytes: {output_wav}")

        return output_wav

    @staticmethod
    def transcode_to_mp3(wav_path: Path, mp3_path: Path, bitrate: str = "192k") -> Path:
        """Convert a WAV audio file to standard MP3 using libmp3lame."""
        mp3_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            str(FFMPEG_PATH),
            "-y",
            "-i", str(wav_path),
            "-c:a", "libmp3lame",
            "-b:a", bitrate,
            str(mp3_path)
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg MP3 transcoding failed: {res.stderr}")
        return mp3_path

    @staticmethod
    def remux_video_with_audio(
        video_input: Path,
        audio_input: Path,
        output_video_mp4: Path
    ) -> Path:
        """Combine original video stream with newly translated audio track into dubbed MP4.
        
        Preserves original video frames without re-encoding (-c:v copy) for ultra-fast processing.
        """
        output_video_mp4.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            str(FFMPEG_PATH),
            "-y",
            "-i", str(video_input),
            "-i", str(audio_input),
            "-c:v", "copy",              # Fast stream copy for video
            "-c:a", "aac",               # High quality AAC audio
            "-b:a", "192k",
            "-map", "0:v:0",             # First video stream from input 0
            "-map", "1:a:0",             # First audio stream from input 1 (translated audio)
            "-shortest",                 # Avoid trailing hangs
            str(output_video_mp4)
        ]
        logger.info(f"Remuxing dubbed video: {' '.join(cmd)}")
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=300)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg video remuxing failed: {res.stderr}")
        return output_video_mp4

    @staticmethod
    def format_srt_time(ms: int) -> str:
        """Format milliseconds into SubRip timestamp: HH:MM:SS,mmm"""
        total_seconds = ms // 1000
        millis = ms % 1000
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"

    @staticmethod
    def format_vtt_time(ms: int) -> str:
        """Format milliseconds into WebVTT timestamp: HH:MM:SS.mmm"""
        total_seconds = ms // 1000
        millis = ms % 1000
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"

    @staticmethod
    def generate_srt(segments: List[Dict[str, Any]]) -> str:
        """Generate standard SubRip (.srt) subtitle file content from timestamped segments."""
        lines = []
        counter = 1
        for seg in segments:
            text = (seg.get("text") or "").strip()
            if not text:
                continue
            start_str = MediaProcessor.format_srt_time(seg.get("start_ms", 0))
            end_str = MediaProcessor.format_srt_time(seg.get("end_ms", seg.get("start_ms", 0) + 1000))
            lines.append(f"{counter}")
            lines.append(f"{start_str} --> {end_str}")
            lines.append(text)
            lines.append("")
            counter += 1
        return "\n".join(lines)

    @staticmethod
    def generate_vtt(segments: List[Dict[str, Any]]) -> str:
        """Generate standard WebVTT (.vtt) subtitle file content from timestamped segments."""
        lines = ["WEBVTT", ""]
        counter = 1
        for seg in segments:
            text = (seg.get("text") or "").strip()
            if not text:
                continue
            start_str = MediaProcessor.format_vtt_time(seg.get("start_ms", 0))
            end_str = MediaProcessor.format_vtt_time(seg.get("end_ms", seg.get("start_ms", 0) + 1000))
            lines.append(f"{counter}")
            lines.append(f"{start_str} --> {end_str}")
            lines.append(text)
            lines.append("")
            counter += 1
        return "\n".join(lines)


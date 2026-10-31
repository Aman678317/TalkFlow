"""Audio reassembly, multi-format export, subtitle generation, and video dubbing engine."""
from __future__ import annotations

import base64
import io
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import wave

from orchestrator.media import MediaProcessor

logger = logging.getLogger("talkflow.orchestrator.reassembler")


class AudioReassembler:
    """Reassembles ordered synthesized audio chunks into a complete continuous audio track and export suite."""

    @staticmethod
    def reassemble_chunks(
        chunk_wav_bytes_list: List[bytes],
        output_file_path: Optional[Path] = None,
        pause_duration_ms: int = 150,
        target_sample_rate: int = 24000
    ) -> Tuple[bytes, int, str]:
        """Reassembles ordered WAV chunks into a single seamless WAV track.
        
        Args:
            chunk_wav_bytes_list: List of valid WAV byte streams ordered by chunk_index.
            output_file_path: Optional destination Path to save the final WAV file on disk.
            pause_duration_ms: Clean silence pause inserted between consecutive chunks.
            target_sample_rate: Expected sample rate (default 24 kHz for neural TTS).
            
        Returns:
            (full_wav_bytes, total_duration_ms, base64_str)
        """
        if not chunk_wav_bytes_list:
            raise ValueError("No audio chunks provided for reassembly.")

        accumulated_frames: List[bytes] = []
        nchannels = 1
        sampwidth = 2
        framerate = target_sample_rate

        # Generate inter-chunk pause silence buffer
        silence_frame_count = int(framerate * (pause_duration_ms / 1000.0))
        silence_bytes = b"\x00" * (silence_frame_count * nchannels * sampwidth)

        total_audio_frames = 0

        for i, chunk_bytes in enumerate(chunk_wav_bytes_list):
            try:
                with wave.open(io.BytesIO(chunk_bytes), "rb") as wf:
                    nchannels = wf.getnchannels()
                    sampwidth = wf.getsampwidth()
                    framerate = wf.getframerate()
                    frames = wf.readframes(wf.getnframes())
                    accumulated_frames.append(frames)
                    total_audio_frames += wf.getnframes()

                    # Append clean pause between chunks, but not after the last chunk
                    if i < len(chunk_wav_bytes_list) - 1 and pause_duration_ms > 0:
                        accumulated_frames.append(silence_bytes)
                        total_audio_frames += silence_frame_count
            except Exception as e:
                logger.error(f"Error reading chunk {i} during reassembly: {e}")

        # Assemble into single continuous WAV buffer
        out_buf = io.BytesIO()
        with wave.open(out_buf, "wb") as out_wf:
            out_wf.setnchannels(nchannels)
            out_wf.setsampwidth(sampwidth)
            out_wf.setframerate(framerate)
            for f in accumulated_frames:
                out_wf.writeframes(f)

        full_wav_bytes = out_buf.getvalue()
        total_duration_ms = int((total_audio_frames / float(framerate)) * 1000)

        # Save WAV to disk
        if output_file_path:
            output_file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_file_path, "wb") as f:
                f.write(full_wav_bytes)
            logger.info(f"Reassembled complete WAV saved to: {output_file_path} ({total_duration_ms}ms)")

        b64_str = base64.b64encode(full_wav_bytes).decode("ascii")
        return full_wav_bytes, total_duration_ms, b64_str

    @staticmethod
    def build_export_deliverables(
        target_lang: str,
        full_wav_path: Path,
        segments: List[Dict[str, Any]],
        full_transcript_text: str,
        artifacts_dir: Path,
        source_video_path: Optional[Path] = None
    ) -> Dict[str, str]:
        """Produce the complete mandatory deliverable suite for a target language.
        
        Required outputs for audio:
        - translated_audio.mp3
        - translated_audio.wav
        - translated_transcript.txt
        - translated_subtitles.srt
        - translated_subtitles.vtt
        - translated_segments.json

        Required outputs for video:
        - translated_video.mp4 (dubbed video)
        - translated_video_audio.mp3
        - translated_video_subtitles.srt
        - translated_video_transcript.txt
        """
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        paths: Dict[str, str] = {}

        # 1. translated_audio.wav
        wav_dest = artifacts_dir / f"translated_audio_{target_lang}.wav"
        if full_wav_path != wav_dest:
            wav_dest.write_bytes(full_wav_path.read_bytes())
        paths["wav"] = str(wav_dest)

        # 2. translated_audio.mp3
        mp3_dest = artifacts_dir / f"translated_audio_{target_lang}.mp3"
        MediaProcessor.transcode_to_mp3(wav_dest, mp3_dest)
        paths["mp3"] = str(mp3_dest)

        # 3. translated_transcript.txt
        txt_dest = artifacts_dir / f"translated_transcript_{target_lang}.txt"
        txt_dest.write_text(full_transcript_text, encoding="utf-8")
        paths["txt"] = str(txt_dest)

        # 4. translated_subtitles.srt
        srt_content = MediaProcessor.generate_srt(segments)
        srt_dest = artifacts_dir / f"translated_subtitles_{target_lang}.srt"
        srt_dest.write_text(srt_content, encoding="utf-8")
        paths["srt"] = str(srt_dest)

        # 5. translated_subtitles.vtt
        vtt_content = MediaProcessor.generate_vtt(segments)
        vtt_dest = artifacts_dir / f"translated_subtitles_{target_lang}.vtt"
        vtt_dest.write_text(vtt_content, encoding="utf-8")
        paths["vtt"] = str(vtt_dest)

        # 6. translated_segments.json
        json_dest = artifacts_dir / f"translated_segments_{target_lang}.json"
        with open(json_dest, "w", encoding="utf-8") as f:
            json.dump(segments, f, indent=2, ensure_ascii=False)
        paths["json"] = str(json_dest)

        # 7. Video Dubbing deliverables (if original media was video)
        if source_video_path and source_video_path.exists():
            # translated_video.mp4
            video_dest = artifacts_dir / f"translated_video_{target_lang}.mp4"
            MediaProcessor.remux_video_with_audio(
                video_input=source_video_path,
                audio_input=wav_dest,
                output_video_mp4=video_dest
            )
            paths["mp4"] = str(video_dest)
            paths["video_audio"] = str(mp3_dest)
            paths["video_subtitles"] = str(srt_dest)
            paths["video_transcript"] = str(txt_dest)

        return paths

"""Intelligent audio chunking and segmentation engine for long audio recordings (5-60+ mins)."""
from __future__ import annotations

import io
import math
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from orchestrator.models import AudioChunkDescriptor
from orchestrator.media import MediaProcessor


class AudioChunker:
    """Divides long audio recordings into discrete, manageable, timestamp-preserving chunks."""

    @staticmethod
    def slice_wav_bytes(
        audio_bytes: bytes,
        chunk_duration_sec: float = 15.0,
        overlap_sec: float = 0.5,
        min_chunk_duration_sec: float = 2.0
    ) -> Tuple[List[AudioChunkDescriptor], List[bytes], int]:
        """Slices incoming audio bytes (WAV, MP3, etc.) into sequential standard-compliant WAV chunks.
        
        Args:
            audio_bytes: Raw audio byte buffer.
            chunk_duration_sec: Target chunk duration in seconds (e.g. 15-30s).
            overlap_sec: Context overlap around boundaries (0.5-1.5s) to avoid clipping words.
            min_chunk_duration_sec: Minimum duration for trailing chunk.
            
        Returns:
            (chunk_descriptors, raw_chunk_wav_bytes_list, total_duration_ms)
        """
        # Ensure we have valid WAV bytes. If not, transcode via MediaProcessor
        canonical_bytes = audio_bytes
        if not audio_bytes.startswith(b"RIFF"):
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".raw", delete=False) as tmp_in:
                tmp_in.write(audio_bytes)
                tmp_in_path = Path(tmp_in.name)
            tmp_out_path = tmp_in_path.with_suffix(".wav")
            try:
                MediaProcessor.extract_canonical_audio(tmp_in_path, tmp_out_path, target_sample_rate=16000)
                canonical_bytes = tmp_out_path.read_bytes()
            finally:
                if tmp_in_path.exists():
                    tmp_in_path.unlink()
                if tmp_out_path.exists():
                    tmp_out_path.unlink()

        with wave.open(io.BytesIO(canonical_bytes), "rb") as wf:
            framerate = wf.getframerate()
            nchannels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            total_frames = wf.getnframes()
            total_duration_sec = total_frames / float(framerate)
            total_duration_ms = int(total_duration_sec * 1000)

            frames_per_chunk = int(framerate * chunk_duration_sec)
            overlap_frames = int(framerate * overlap_sec) if overlap_sec > 0 else 0
            stride_frames = max(1, frames_per_chunk - overlap_frames)
            
            total_chunks = max(1, math.ceil(total_frames / stride_frames))

            descriptors: List[AudioChunkDescriptor] = []
            chunk_bytes_list: List[bytes] = []

            for idx in range(total_chunks):
                start_frame = idx * stride_frames
                if start_frame >= total_frames:
                    break
                
                frames_to_read = min(frames_per_chunk, total_frames - start_frame)
                wf.setpos(start_frame)
                raw_frames = wf.readframes(frames_to_read)

                # Standalone standard WAV buffer with 44-byte RIFF header
                chunk_buf = io.BytesIO()
                with wave.open(chunk_buf, "wb") as out_wf:
                    out_wf.setnchannels(nchannels)
                    out_wf.setsampwidth(sampwidth)
                    out_wf.setframerate(framerate)
                    out_wf.writeframes(raw_frames)
                chunk_bytes = chunk_buf.getvalue()

                start_ms = int((start_frame / framerate) * 1000)
                duration_ms = int((frames_to_read / framerate) * 1000)
                end_ms = start_ms + duration_ms

                desc = AudioChunkDescriptor(
                    chunk_index=idx,
                    total_chunks=total_chunks,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    duration_ms=duration_ms,
                    status="PENDING"
                )
                descriptors.append(desc)
                chunk_bytes_list.append(chunk_bytes)

        # Update actual count in descriptors
        for d in descriptors:
            d.total_chunks = len(descriptors)

        return descriptors, chunk_bytes_list, total_duration_ms

    @staticmethod
    def slice_media_file(
        file_path: Path,
        chunk_duration_sec: float = 15.0,
        overlap_sec: float = 0.5
    ) -> Tuple[List[AudioChunkDescriptor], List[bytes], int, Path]:
        """Extract canonical 16kHz audio from file on disk and slice into chunks.
        
        Returns:
            (descriptors, chunk_bytes_list, total_duration_ms, canonical_wav_path)
        """
        canonical_wav = file_path.with_name(f"{file_path.stem}_canonical_16k.wav")
        MediaProcessor.extract_canonical_audio(file_path, canonical_wav, target_sample_rate=16000)
        audio_bytes = canonical_wav.read_bytes()
        descriptors, chunks, total_ms = AudioChunker.slice_wav_bytes(
            audio_bytes,
            chunk_duration_sec=chunk_duration_sec,
            overlap_sec=overlap_sec
        )
        return descriptors, chunks, total_ms, canonical_wav

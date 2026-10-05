"""
HospitalRobotNav — Speech Audio Processor & Format Normalizer
============================================================
Handles incoming audio format inspection, validation, conversion,
and VAD normalization for the faster-whisper speech recognition pipeline.

Ensures:
1. Audio format inspection printed ONCE per session:
   codec, sample rate, channels, bit depth, encoding, duration.
2. WebM/Opus / WAV / raw PCM decoding to clean 16 kHz mono Float32 numpy array.
3. Silence/energy calculation for VAD pre-screening.
4. Zero unnecessary multiple resampling passes.
"""

from __future__ import annotations

import io
import struct
import wave
from typing import Any, Dict, Optional, Tuple
import numpy as np


class AudioProcessor:
    """
    Standardizes audio streams and chunks into the 16,000 Hz mono Float32 format
    required by faster-whisper.
    """

    def __init__(self, target_sample_rate: int = 16000) -> None:
        self.target_sample_rate = target_sample_rate
        self._format_inspected: bool = False
        self._last_format_info: Dict[str, Any] = {}

    def inspect_and_log_format_once(
        self,
        raw_bytes: bytes,
        declared_rate: int = 16000,
        declared_channels: int = 1,
    ) -> Dict[str, Any]:
        """
        Inspect the audio format and log diagnostic parameters once per session.
        """
        if self._format_inspected and self._last_format_info:
            return self._last_format_info

        codec = "PCM_S16LE"
        sample_rate = declared_rate
        channels = declared_channels
        bit_depth = 16
        encoding = "Little-Endian Signed Integer"
        duration_sec = 0.0

        # Check for standard container signatures
        if raw_bytes.startswith(b"RIFF") and b"WAVE" in raw_bytes[:16]:
            try:
                with wave.open(io.BytesIO(raw_bytes), "rb") as wf:
                    codec = "WAV_PCM"
                    channels = wf.getnchannels()
                    bit_depth = wf.getsampwidth() * 8
                    sample_rate = wf.getframerate()
                    duration_sec = wf.getnframes() / float(sample_rate) if sample_rate else 0.0
            except Exception:
                pass
        elif raw_bytes.startswith(b"\x1a\x45\xdf\xa3"):
            codec = "WebM/EBML"
            encoding = "Compressed Opus/Vorbis"
        elif len(raw_bytes) >= 2:
            duration_sec = (len(raw_bytes) // 2) / float(sample_rate)

        info = {
            "codec": codec,
            "sample_rate": sample_rate,
            "channels": channels,
            "bit_depth": bit_depth,
            "encoding": encoding,
            "duration": round(duration_sec, 2),
            "byte_length": len(raw_bytes),
        }
        self._last_format_info = info
        self._format_inspected = True

        print(
            f"[AUDIO FORMAT] codec: {codec} | sample_rate: {sample_rate}Hz | "
            f"channels: {channels} | bit_depth: {bit_depth}-bit | "
            f"encoding: {encoding} | duration: {info['duration']}s"
        )
        return info

    def to_float32_16khz(
        self,
        audio_input: bytes | np.ndarray,
        source_rate: int = 16000,
        source_channels: int = 1,
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Convert input raw bytes (PCM, WAV, or container) or numpy array into
        a 1D mono Float32 numpy array sampled at 16,000 Hz, with amplitudes normalized to [-1.0, 1.0].
        """
        if isinstance(audio_input, np.ndarray):
            audio = audio_input.astype(np.float32)
            if audio.ndim > 1:
                audio = np.mean(audio, axis=1)  # downmix to mono
            # Normalize if integer range
            if np.max(np.abs(audio)) > 1.0:
                audio = audio / 32768.0
            return audio, {"channels": 1, "sample_rate": source_rate}

        raw_bytes = bytes(audio_input)
        if not raw_bytes:
            return np.zeros(0, dtype=np.float32), {"channels": 1, "sample_rate": 16000}

        # Inspect format on first arrival
        fmt_info = self.inspect_and_log_format_once(raw_bytes, source_rate, source_channels)

        # 1. Try standard WAV container parsing
        if raw_bytes.startswith(b"RIFF") and b"WAVE" in raw_bytes[:16]:
            try:
                with wave.open(io.BytesIO(raw_bytes), "rb") as wf:
                    n_channels = wf.getnchannels()
                    sampwidth = wf.getsampwidth()
                    framerate = wf.getframerate()
                    n_frames = wf.getnframes()
                    raw_pcm = wf.readframes(n_frames)

                    if sampwidth == 2:
                        audio = np.frombuffer(raw_pcm, dtype=np.int16).astype(np.float32) / 32768.0
                    elif sampwidth == 1:
                        audio = (np.frombuffer(raw_pcm, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
                    elif sampwidth == 4:
                        audio = np.frombuffer(raw_pcm, dtype=np.int32).astype(np.float32) / 2147483648.0
                    else:
                        audio = np.frombuffer(raw_pcm, dtype=np.int16).astype(np.float32) / 32768.0

                    if n_channels > 1:
                        audio = audio.reshape(-1, n_channels).mean(axis=1)

                    if framerate != self.target_sample_rate and len(audio) > 0:
                        audio = self._resample(audio, framerate, self.target_sample_rate)

                    return audio, fmt_info
            except Exception as e:
                print(f"[AUDIO] Notice: WAV parse exception ({e}), falling back to direct PCM decode")

        # 2. Try soundfile for complex containers (WebM, OGG, FLAC)
        if raw_bytes.startswith(b"\x1a\x45\xdf\xa3") or raw_bytes.startswith(b"OggS"):
            try:
                import soundfile as sf
                data, sr = sf.read(io.BytesIO(raw_bytes), dtype="float32")
                if data.ndim > 1:
                    data = data.mean(axis=1)
                if sr != self.target_sample_rate:
                    data = self._resample(data, sr, self.target_sample_rate)
                return data, fmt_info
            except Exception as ex:
                print(f"[AUDIO] Container decode exception: {ex}")

        # 3. Default: Raw Little-Endian 16-bit Signed PCM
        # Ensure byte length is even
        if len(raw_bytes) % 2 != 0:
            raw_bytes = raw_bytes[: len(raw_bytes) - (len(raw_bytes) % 2)]

        samples = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        if source_channels > 1 and len(samples) >= source_channels:
            samples = samples.reshape(-1, source_channels).mean(axis=1)

        if source_rate != self.target_sample_rate and len(samples) > 0:
            samples = self._resample(samples, source_rate, self.target_sample_rate)

        return samples, fmt_info

    def _resample(self, audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
        """Single-pass high quality audio resampler."""
        if orig_sr == target_sr or len(audio) == 0:
            return audio
        try:
            from scipy import signal
            num_target_samples = int(round(len(audio) * float(target_sr) / orig_sr))
            resampled = signal.resample(audio, num_target_samples)
            return resampled.astype(np.float32)
        except Exception:
            # Fallback linear interpolation
            duration = len(audio) / float(orig_sr)
            target_len = int(round(duration * target_sr))
            orig_indices = np.linspace(0, len(audio) - 1, len(audio))
            target_indices = np.linspace(0, len(audio) - 1, target_len)
            return np.interp(target_indices, orig_indices, audio).astype(np.float32)

    def calculate_energy_rms(self, audio: np.ndarray) -> float:
        """Calculate Root Mean Square (RMS) energy."""
        if len(audio) == 0:
            return 0.0
        return float(np.sqrt(np.mean(np.square(audio))))

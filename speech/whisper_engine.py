"""
HospitalRobotNav — faster-whisper STT Engine
============================================
High-performance speech-to-text inference using CTranslate2 and faster-whisper.

Rules:
1. Model loads ONCE on initialization and remains resident.
2. Runs in a dedicated STT process outside Isaac Sim.
3. Safe inference settings (conservative beam search, Silero VAD, no hallucinations).
4. No text fabrication or artificial hard-coding.
"""

from __future__ import annotations

import os
import re
import string
import time
from typing import Any, Dict, List, Optional, Tuple
import numpy as np


class WhisperEngine:
    """
    Persistent faster-whisper recognition engine.
    """

    def __init__(
        self,
        model_size: str = "small",
        device: str = "cpu",
        compute_type: Optional[str] = None,
        cpu_threads: int = 4,
    ) -> None:
        self.model_size = model_size
        self.device = device.lower()
        self.cpu_threads = cpu_threads

        # Determine compute_type
        if compute_type:
            self.compute_type = compute_type
        elif self.device == "cuda":
            self.compute_type = "float16"
        else:
            self.compute_type = "int8"

        self.model = None
        self.is_ready = False
        self._load_model()

    def _load_model(self) -> None:
        """Load faster-whisper model once into memory."""
        print(f"[STT] Model loading: {self.model_size} (device: {self.device}, compute_type: {self.compute_type})...")
        t0 = time.time()
        try:
            from faster_whisper import WhisperModel

            self.model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
                cpu_threads=self.cpu_threads,
            )
            self.is_ready = True
            load_sec = time.time() - t0
            print(f"[STT] Model ready in {load_sec:.2f}s")
        except Exception as e:
            self.is_ready = False
            print(f"[STT ERROR] Failed to load model {self.model_size} on {self.device}: {e}")
            if self.device != "cpu":
                print("[STT] Falling back to CPU int8...")
                self.device = "cpu"
                self.compute_type = "int8"
                from faster_whisper import WhisperModel

                self.model = WhisperModel(
                    self.model_size,
                    device="cpu",
                    compute_type="int8",
                    cpu_threads=self.cpu_threads,
                )
                self.is_ready = True
                print(f"[STT] CPU Model ready in {time.time() - t0:.2f}s")
            else:
                raise

    def transcribe(
        self,
        audio_float32: np.ndarray,
        language: Optional[str] = "en",
    ) -> Dict[str, Any]:
        """
        Transcribe a 16 kHz mono Float32 audio array using faster-whisper.

        Returns structured dict:
            {
                "success": bool,
                "transcript": str,
                "language": str,
                "language_prob": float,
                "duration": float,
                "latency_ms": float,
                "segments": List[Dict[str, Any]],
                "error": Optional[str]
            }
        """
        if not self.is_ready or self.model is None:
            return {
                "success": False,
                "transcript": "",
                "error": "Model not loaded",
                "latency_ms": 0.0,
            }

        if len(audio_float32) == 0:
            return {
                "success": True,
                "transcript": "",
                "language": language or "en",
                "duration": 0.0,
                "latency_ms": 0.0,
            }

        audio_duration = len(audio_float32) / 16000.0
        print(f"[STT] Audio received: {audio_duration:.2f}s | Transcribing...")
        t0 = time.time()

        try:
            # Conservative decoding settings for command recognition
            segments_gen, info = self.model.transcribe(
                audio_float32,
                language=language,
                beam_size=5,
                best_of=5,
                temperature=0.0,
                condition_on_previous_text=False,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=400),
                no_speech_threshold=0.6,
            )

            raw_segments = list(segments_gen)
            full_text = " ".join(seg.text for seg in raw_segments)
            clean_text = self._normalize_transcript(full_text)
            latency_ms = (time.time() - t0) * 1000.0

            print(f"[STT] Final: \"{clean_text}\" | Processing time: {latency_ms / 1000.0:.2f}s")

            return {
                "success": True,
                "transcript": clean_text,
                "language": info.language,
                "language_prob": float(info.language_probability) if hasattr(info, "language_probability") else 1.0,
                "duration": round(info.duration, 2),
                "latency_ms": round(latency_ms, 1),
                "error": None,
            }
        except Exception as e:
            latency_ms = (time.time() - t0) * 1000.0
            print(f"[STT ERROR] Transcription exception: {e}")
            return {
                "success": False,
                "transcript": "",
                "error": str(e),
                "latency_ms": round(latency_ms, 1),
            }

    @staticmethod
    def _normalize_transcript(text: str) -> str:
        """
        Perform safe transcript normalization:
        - Trim whitespace
        - Collapse multiple spaces
        - Normalize casing and remove trailing punctuation like '.' or '?'
        """
        if not text:
            return ""
        s = text.strip()
        # Remove trailing sentence punctuation
        s = re.sub(r"[.?!]+$", "", s).strip()
        # Collapse multiple spaces
        s = re.sub(r"\s+", " ", s)
        return s

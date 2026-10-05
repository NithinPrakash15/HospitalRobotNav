"""
HospitalRobotNav — Audio Capture
===================================
Thread-safe microphone stream manager with Voice Activity Detection (VAD).

Responsibilities:
    - Open the default system microphone via ``sounddevice``
    - Stream 16 kHz mono int16 audio chunks into a thread-safe ring buffer
    - Provide energy-based Voice Activity Detection (VAD)
    - Gracefully fall back to ``NO_MICROPHONE`` mode when hardware is absent

Threading Model:
    ``AudioCapture.start()`` spawns a daemon thread that continuously fills
    the ring buffer.  Consumers call ``read_chunk()`` or ``read_utterance()``
    from any thread — all access is synchronised via a ``threading.Lock``.

ROS2 Deployment Note:
    Maps to an ``audio_capture_node`` publishing ``audio_msgs/msg/Audio``
    on the ``/audio_raw`` topic at the configured chunk rate.

Reference:
    ITU-T P.56 — Objective measurement of active speech level.
"""

from __future__ import annotations

import math
import struct
import threading
import time
from collections import deque
from typing import Deque, List, Optional

import numpy as np

from speech.speech_config import SPEECH_CONFIG, SpeechPipelineState
from utilities.logger import get_logger

log = get_logger(__name__)

# Try to import sounddevice; if unavailable, flag gracefully
try:
    import sounddevice as sd
    _SOUNDDEVICE_AVAILABLE = True
except (ImportError, OSError):
    _SOUNDDEVICE_AVAILABLE = False
    log.debug("sounddevice not available — audio capture disabled.")


# ─────────────────────────────────────────────────────────────────────────────
# Audio Chunk Wrapper
# ─────────────────────────────────────────────────────────────────────────────

class AudioChunk:
    """A single chunk of raw PCM audio with metadata.

    Attributes:
        data:       Raw PCM bytes (int16, mono, 16 kHz).
        samples:    NumPy int16 array view of the data.
        rms_energy: Root-mean-square energy of the chunk.
        timestamp:  Wall-clock time when the chunk was captured.
        is_speech:  Whether VAD classifies this chunk as speech.
    """

    __slots__ = ("data", "samples", "rms_energy", "timestamp", "is_speech")

    def __init__(self, data: bytes, timestamp: float) -> None:
        self.data = data
        self.timestamp = timestamp

        # Convert to numpy for energy computation
        self.samples: np.ndarray = np.frombuffer(data, dtype=np.int16)

        # RMS energy
        if len(self.samples) > 0:
            self.rms_energy = float(np.sqrt(np.mean(self.samples.astype(np.float64) ** 2)))
        else:
            self.rms_energy = 0.0

        # VAD decision
        self.is_speech = self.rms_energy > SPEECH_CONFIG.audio.VAD_ENERGY_THRESHOLD

    def __repr__(self) -> str:
        tag = "SPEECH" if self.is_speech else "SILENT"
        return f"AudioChunk({tag}, rms={self.rms_energy:.0f}, {len(self.samples)} smp)"


# ─────────────────────────────────────────────────────────────────────────────
# Audio Capture Engine
# ─────────────────────────────────────────────────────────────────────────────

class AudioCapture:
    """Thread-safe microphone capture with ring buffer and VAD.

    Lifecycle::

        cap = AudioCapture()
        cap.start()          # spawns capture thread

        # Consumer loop (any thread):
        chunk = cap.read_chunk()       # blocking, returns AudioChunk
        utterance = cap.read_utterance()  # blocking, returns list[AudioChunk]

        cap.stop()           # joins capture thread

    Attributes:
        is_available:  True if a microphone was successfully opened.
        is_running:    True while the capture thread is alive.
        state:         Current pipeline state string.
    """

    def __init__(self) -> None:
        self._cfg = SPEECH_CONFIG.audio

        # Ring buffer of AudioChunk objects
        self._buffer: Deque[AudioChunk] = deque(maxlen=self._cfg.RING_BUFFER_CHUNKS)
        self._lock = threading.Lock()
        self._chunk_ready = threading.Event()

        # Thread management
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._device_index: Optional[int] = None

        # State
        self.is_available: bool = _SOUNDDEVICE_AVAILABLE
        self.is_running: bool = False
        self.state: str = SpeechPipelineState.IDLE

        # Statistics
        self._total_chunks: int = 0
        self._speech_chunks: int = 0

    def select_device(self, device_index: Optional[int] = None) -> Optional[int]:
        """Choose a usable input device, falling back to the default microphone."""
        if not _SOUNDDEVICE_AVAILABLE or sd is None:
            return None

        try:
            if device_index is not None:
                self._device_index = device_index
                return device_index

            devices = sd.query_devices()
            if isinstance(devices, tuple):
                devices = [devices]

            for idx, info in enumerate(devices):
                if isinstance(info, dict):
                    if info.get("max_input_channels", 0) > 0:
                        self._device_index = idx
                        return idx
            default_device = sd.default.device
            if default_device is not None:
                self._device_index = default_device[0] if isinstance(default_device, tuple) else default_device
                return self._device_index
        except Exception:
            log.debug("AudioCapture: Device discovery failed; using default system input.")

        self._device_index = None
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Start the microphone capture thread.

        Returns:
            True if capture started successfully, False if no mic available.
        """
        if not self.is_available:
            log.warning("AudioCapture: No microphone available — running in text-input mode.")
            self.state = SpeechPipelineState.DISABLED
            return False

        if self.is_running:
            log.warning("AudioCapture: Already running.")
            return True

        self.select_device()
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._capture_loop,
            name="AudioCapture-Thread",
            daemon=True,
        )
        self._thread.start()
        self.is_running = True
        self.state = SpeechPipelineState.IDLE
        log.info(
            "AudioCapture started: %d Hz, %d ch, %d ms chunks on device %s.",
            self._cfg.SAMPLE_RATE,
            self._cfg.CHANNELS,
            self._cfg.CHUNK_DURATION_MS,
            self._device_index,
        )
        return True

    def stop(self) -> None:
        """Stop the capture thread and release the microphone."""
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self.is_running = False
        self.state = SpeechPipelineState.DISABLED
        log.info(
            "AudioCapture stopped. Total chunks: %d, speech chunks: %d.",
            self._total_chunks,
            self._speech_chunks,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Consumer API
    # ─────────────────────────────────────────────────────────────────────────

    def read_chunk(self, timeout: float = 1.0) -> Optional[AudioChunk]:
        """Read the next audio chunk (blocking).

        Args:
            timeout: Max seconds to wait for a chunk.

        Returns:
            An AudioChunk, or None if timed out or stopped.
        """
        if not self.is_running:
            return None

        if self._chunk_ready.wait(timeout=timeout):
            with self._lock:
                if self._buffer:
                    chunk = self._buffer.popleft()
                    # Reset event only when buffer is empty
                    if not self._buffer:
                        self._chunk_ready.clear()
                    return chunk
        return None

    def read_utterance(self, timeout: float = 15.0) -> List[AudioChunk]:
        """Read a complete speech utterance delimited by silence.

        Blocks until VAD detects speech onset, then collects chunks until
        VAD silence threshold is reached or the safety cap fires.

        Args:
            timeout: Max seconds to wait for speech onset.

        Returns:
            List of AudioChunks forming the utterance (may be empty on timeout).
        """
        utterance: List[AudioChunk] = []
        silence_count = 0
        speech_started = False
        start_time = time.monotonic()

        while not self._stop_event.is_set():
            elapsed = time.monotonic() - start_time

            # Timeout waiting for speech onset
            if not speech_started and elapsed > timeout:
                return []

            chunk = self.read_chunk(timeout=0.5)
            if chunk is None:
                continue

            if chunk.is_speech:
                speech_started = True
                silence_count = 0
                utterance.append(chunk)
            elif speech_started:
                silence_count += 1
                utterance.append(chunk)  # include trailing silence

                # Silence threshold reached → utterance complete
                if silence_count >= self._cfg.VAD_SILENCE_FRAMES:
                    break

            # Safety cap on utterance length
            if len(utterance) >= self._cfg.MAX_UTTERANCE_CHUNKS:
                log.warning("AudioCapture: Utterance hit safety cap (%d chunks).",
                            self._cfg.MAX_UTTERANCE_CHUNKS)
                break

        return utterance

    def get_utterance_bytes(self, utterance: List[AudioChunk]) -> bytes:
        """Concatenate utterance chunks into a single PCM byte string.

        Args:
            utterance: List of AudioChunks from read_utterance().

        Returns:
            Raw PCM bytes suitable for passing to the speech recogniser.
        """
        return b"".join(chunk.data for chunk in utterance)

    def get_utterance_duration(self, utterance: List[AudioChunk]) -> float:
        """Calculate the duration of an utterance in seconds.

        Args:
            utterance: List of AudioChunks.

        Returns:
            Duration in seconds.
        """
        total_samples = sum(len(c.samples) for c in utterance)
        return total_samples / self._cfg.SAMPLE_RATE

    # ─────────────────────────────────────────────────────────────────────────
    # Statistics
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def speech_ratio(self) -> float:
        """Fraction of captured chunks classified as speech."""
        if self._total_chunks == 0:
            return 0.0
        return self._speech_chunks / self._total_chunks

    @property
    def buffer_level(self) -> int:
        """Number of chunks currently in the ring buffer."""
        with self._lock:
            return len(self._buffer)

    # ─────────────────────────────────────────────────────────────────────────
    # Internal Capture Loop
    # ─────────────────────────────────────────────────────────────────────────

    def _capture_loop(self) -> None:
        """Background thread: continuously read from the microphone."""
        device = self._device_index
        try:
            with sd.RawInputStream(
                samplerate=self._cfg.SAMPLE_RATE,
                blocksize=self._cfg.CHUNK_SIZE,
                dtype=self._cfg.DTYPE,
                channels=self._cfg.CHANNELS,
                device=device,
            ) as stream:
                log.info("AudioCapture: Microphone stream opened on device %s.", device)

                while not self._stop_event.is_set():
                    raw_data, overflowed = stream.read(self._cfg.CHUNK_SIZE)
                    if overflowed:
                        log.debug("AudioCapture: Input overflow detected.")

                    chunk = AudioChunk(
                        data=bytes(raw_data),
                        timestamp=time.monotonic(),
                    )

                    self._total_chunks += 1
                    if chunk.is_speech:
                        self._speech_chunks += 1

                    with self._lock:
                        self._buffer.append(chunk)
                        self._chunk_ready.set()

        except sd.PortAudioError as exc:
            log.error("AudioCapture: PortAudio error — %s", exc)
            self.is_available = False
            self.state = SpeechPipelineState.ERROR

        except Exception as exc:
            log.error("AudioCapture: Unexpected error — %s", exc)
            self.state = SpeechPipelineState.ERROR

        finally:
            self.is_running = False
            log.info("AudioCapture: Capture loop exited.")

    # ─────────────────────────────────────────────────────────────────────────
    # Diagnostic Methods (used by voice_diagnostic.py)
    # ─────────────────────────────────────────────────────────────────────────

    def get_device_info(self) -> dict:
        """Return information about the current audio input device.

        Returns:
            Dict with 'name', 'index', 'sample_rate', 'channels', 'available'.
        """
        if not _SOUNDDEVICE_AVAILABLE or sd is None:
            return {
                "name": "No audio backend",
                "index": -1,
                "sample_rate": 0,
                "channels": 0,
                "available": False,
            }
        try:
            if self._device_index is not None:
                info = sd.query_devices(self._device_index)
            else:
                info = sd.query_devices(kind="input")
            return {
                "name": info.get("name", "Unknown") if isinstance(info, dict) else str(info),
                "index": self._device_index,
                "sample_rate": self._cfg.SAMPLE_RATE,
                "channels": self._cfg.CHANNELS,
                "available": True,
            }
        except Exception as exc:
            return {
                "name": f"Error: {exc}",
                "index": self._device_index,
                "sample_rate": self._cfg.SAMPLE_RATE,
                "channels": self._cfg.CHANNELS,
                "available": False,
            }

    def get_audio_level(self) -> float:
        """Return the RMS energy of the most recent audio chunk.

        Returns:
            RMS energy as a float, or 0.0 if no data is available.
        """
        with self._lock:
            if self._buffer:
                return self._buffer[-1].rms_energy
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Text Input Fallback
# ─────────────────────────────────────────────────────────────────────────────

class TextInputCapture:
    """Fallback capture that accepts typed text instead of microphone audio.

    Used when no microphone is available or during development/testing.
    Provides the same interface as AudioCapture for downstream compatibility.

    Usage:
        cap = TextInputCapture()
        text = cap.get_text_input("Your command: ")
    """

    def __init__(self) -> None:
        self.is_available: bool = True
        self.is_running: bool = False
        self.state: str = SpeechPipelineState.IDLE
        self._pending_text: Optional[str] = None
        self._lock = threading.Lock()

    def start(self) -> bool:
        """Mark as running (no thread needed for text input)."""
        self.is_running = True
        self.state = SpeechPipelineState.IDLE
        log.info("TextInputCapture: Running in text-input fallback mode.")
        return True

    def stop(self) -> None:
        """Mark as stopped."""
        self.is_running = False
        self.state = SpeechPipelineState.DISABLED

    def submit_text(self, text: str) -> None:
        """Submit text as if it were a spoken command.

        Called from the Pygame event handler when the user types a command
        via the keyboard (e.g., pressing 'T' to open a text input box).

        Args:
            text: The user's typed command string.
        """
        with self._lock:
            self._pending_text = text.strip()

    def consume_text(self) -> Optional[str]:
        """Consume and return any pending text input.

        Returns:
            The submitted text, or None if nothing is pending.
        """
        with self._lock:
            text = self._pending_text
            self._pending_text = None
            return text

    def has_pending(self) -> bool:
        """Check if there is unconsumed text input."""
        with self._lock:
            return self._pending_text is not None

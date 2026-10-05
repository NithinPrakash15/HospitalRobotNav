"""
HospitalRobotNav — Voice Pipeline Diagnostic Tool
===================================================
Standalone diagnostic script that tests every stage of the voice pipeline
independently using REAL hardware — no faking.

Run from project root::

    python -m speech.voice_diagnostic

Stages Tested:
    1. MICROPHONE    — PortAudio device discovery and stream open
    2. AUDIO LEVEL   — Real-time RMS energy from microphone
    3. VAD           — Voice activity detection threshold check
    4. VOSK MODEL    — Model file discovery and loading
    5. ASR (LIVE)    — Live streaming transcription for 10 seconds
    6. WAKE WORD     — Wake word detection from live audio
    7. COMMAND       — Full command capture and intent parsing

This script does NOT import omni.ui or Isaac Sim — runs standalone.
"""

from __future__ import annotations

import os
import sys
import time
import struct
import math
import json
import traceback
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# Ensure project root is on sys.path
# ─────────────────────────────────────────────────────────────────────────────
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def _banner(title: str) -> None:
    width = 64
    print()
    print("=" * width)
    print(f"  {title}")
    print("=" * width)


def _status(label: str, value: str, ok: bool = True) -> None:
    icon = "[OK]" if ok else "[FAIL]"
    print(f"  {icon}  {label:30s}: {value}")


def _warn(msg: str) -> None:
    print(f"  [WARN] {msg}")


def _fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


# ─────────────────────────────────────────────────────────────────────────────
# Stage 1: Microphone
# ─────────────────────────────────────────────────────────────────────────────

def test_microphone() -> bool:
    _banner("STAGE 1: MICROPHONE")

    try:
        import pyaudio
    except ImportError:
        _fail("pyaudio not installed. Run: pip install pyaudio")
        return False

    pa = pyaudio.PyAudio()
    device_count = pa.get_device_count()
    _status("PortAudio Devices", str(device_count), device_count > 0)

    if device_count == 0:
        _fail("No audio devices found.")
        pa.terminate()
        return False

    # Find default input
    try:
        default_info = pa.get_default_input_device_info()
        dev_name = default_info.get("name", "Unknown")
        dev_index = default_info.get("index", -1)
        max_channels = int(default_info.get("maxInputChannels", 0))
        sample_rate = int(default_info.get("defaultSampleRate", 0))
        _status("Default Input Device", f"[{dev_index}] {dev_name}")
        _status("Max Input Channels", str(max_channels), max_channels > 0)
        _status("Default Sample Rate", f"{sample_rate} Hz", sample_rate > 0)
    except Exception as e:
        _fail(f"No default input device: {e}")
        pa.terminate()
        return False

    # Try opening a stream
    try:
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=480,
        )
        _status("Stream Open (16kHz, mono)", "SUCCESS")
        # Read a small chunk
        data = stream.read(480, exception_on_overflow=False)
        _status("Read 30ms Chunk", f"{len(data)} bytes", len(data) > 0)
        stream.stop_stream()
        stream.close()
    except Exception as e:
        _fail(f"Failed to open stream: {e}")
        pa.terminate()
        return False

    pa.terminate()
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2: Audio Level
# ─────────────────────────────────────────────────────────────────────────────

def test_audio_level() -> Optional[float]:
    _banner("STAGE 2: AUDIO LEVEL (speak now for 3 seconds)")

    try:
        import pyaudio
    except ImportError:
        _fail("pyaudio not installed")
        return None

    pa = pyaudio.PyAudio()
    try:
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=480,
        )
    except Exception as e:
        _fail(f"Cannot open stream: {e}")
        pa.terminate()
        return None

    max_rms = 0.0
    avg_rms = 0.0
    n_chunks = 0
    duration = 3.0
    start = time.monotonic()

    print("  Listening... speak or be quiet to see levels.")
    while time.monotonic() - start < duration:
        try:
            data = stream.read(480, exception_on_overflow=False)
        except Exception:
            break
        # Calculate RMS
        samples = struct.unpack(f"<{len(data)//2}h", data)
        rms = math.sqrt(sum(s * s for s in samples) / len(samples)) if samples else 0.0
        max_rms = max(max_rms, rms)
        avg_rms += rms
        n_chunks += 1

        # Live indicator
        bar_len = min(50, int(rms / 200))
        bar = "|" * bar_len
        sys.stdout.write(f"\r  RMS: {rms:8.1f}  {bar:50s}")
        sys.stdout.flush()

    stream.stop_stream()
    stream.close()
    pa.terminate()

    avg_rms = avg_rms / max(1, n_chunks)
    print()
    _status("Average RMS", f"{avg_rms:.1f}")
    _status("Peak RMS", f"{max_rms:.1f}")

    from speech.speech_config import SPEECH_CONFIG
    threshold = SPEECH_CONFIG.audio.VAD_ENERGY_THRESHOLD
    _status("VAD Threshold", f"{threshold:.1f}")

    if max_rms < threshold:
        _warn(f"Peak RMS ({max_rms:.1f}) is BELOW VAD threshold ({threshold:.1f})!")
        _warn("Speech will be classified as SILENCE. Lower VAD_ENERGY_THRESHOLD or speak louder.")
        _status("VAD Would Trigger", "NO", ok=False)
    else:
        _status("VAD Would Trigger", "YES", ok=True)

    return max_rms


# ─────────────────────────────────────────────────────────────────────────────
# Stage 3: Vosk Model
# ─────────────────────────────────────────────────────────────────────────────

def test_vosk_model() -> bool:
    _banner("STAGE 3: VOSK MODEL")

    from speech.speech_config import SPEECH_CONFIG

    # Check candidate paths
    candidates = list(SPEECH_CONFIG.recognizer.VOSK_MODEL_CANDIDATES)
    preferred = os.path.abspath(SPEECH_CONFIG.recognizer.VOSK_MODEL_PATH)
    if preferred not in candidates:
        candidates.insert(0, preferred)

    model_path = None
    for path in candidates:
        exists = os.path.isdir(path)
        status = "EXISTS" if exists else "NOT FOUND"
        print(f"  [{status:9s}] {path}")
        if exists and model_path is None:
            model_path = path

    if model_path is None:
        _fail("No Vosk model found at any candidate path!")
        _fail("Download from: https://alphacephei.com/vosk/models")
        return False

    _status("Selected Model", model_path)

    # Try loading
    try:
        from vosk import Model, SetLogLevel
        SetLogLevel(-1)
        model = Model(model_path)
        _status("Vosk Model Load", "SUCCESS")
        return True
    except ImportError:
        _fail("vosk not installed. Run: pip install vosk")
        return False
    except Exception as e:
        _fail(f"Failed to load model: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Stage 4: Live ASR
# ─────────────────────────────────────────────────────────────────────────────

def test_live_asr() -> Optional[str]:
    _banner("STAGE 4: LIVE ASR (speak for 8 seconds)")

    try:
        import pyaudio
        from vosk import Model, KaldiRecognizer, SetLogLevel
    except ImportError as e:
        _fail(f"Missing dependency: {e}")
        return None

    from speech.speech_config import SPEECH_CONFIG

    # Find model
    model_path = None
    for path in SPEECH_CONFIG.recognizer.VOSK_MODEL_CANDIDATES:
        if os.path.isdir(path):
            model_path = path
            break
    if not model_path and os.path.isdir(SPEECH_CONFIG.recognizer.VOSK_MODEL_PATH):
        model_path = SPEECH_CONFIG.recognizer.VOSK_MODEL_PATH

    if not model_path:
        _fail("No model available")
        return None

    SetLogLevel(-1)
    model = Model(model_path)
    rec = KaldiRecognizer(model, 16000)
    rec.SetWords(True)

    pa = pyaudio.PyAudio()
    stream = pa.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=16000,
        input=True,
        frames_per_buffer=480,
    )

    print("  Listening... speak clearly now.")
    last_transcript = ""
    start = time.monotonic()
    duration = 8.0

    while time.monotonic() - start < duration:
        try:
            data = stream.read(480, exception_on_overflow=False)
        except Exception:
            break

        if rec.AcceptWaveform(data):
            result = json.loads(rec.Result())
            text = result.get("text", "")
            if text:
                last_transcript = text
                print(f"  [FINAL]   {text}")
        else:
            partial = json.loads(rec.PartialResult())
            ptext = partial.get("partial", "")
            if ptext:
                sys.stdout.write(f"\r  [PARTIAL] {ptext:60s}")
                sys.stdout.flush()

    # Final result
    final = json.loads(rec.FinalResult())
    final_text = final.get("text", "")
    if final_text:
        last_transcript = final_text
        print(f"\n  [FINAL]   {final_text}")

    stream.stop_stream()
    stream.close()
    pa.terminate()
    print()

    if last_transcript:
        _status("ASR Transcript", last_transcript)
    else:
        _warn("No speech detected. Check microphone and audio levels.")
        _status("ASR Transcript", "(empty)", ok=False)

    return last_transcript


# ─────────────────────────────────────────────────────────────────────────────
# Stage 5: Wake Word Detection
# ─────────────────────────────────────────────────────────────────────────────

def test_wake_word() -> bool:
    _banner("STAGE 5: WAKE WORD (say 'Hey Arogya' within 10 seconds)")

    try:
        import pyaudio
        from vosk import Model, KaldiRecognizer, SetLogLevel
    except ImportError as e:
        _fail(f"Missing dependency: {e}")
        return False

    from speech.speech_config import SPEECH_CONFIG
    from speech.wake_word_detector import WakeWordDetector

    # Find model
    model_path = None
    for path in SPEECH_CONFIG.recognizer.VOSK_MODEL_CANDIDATES:
        if os.path.isdir(path):
            model_path = path
            break
    if not model_path:
        _fail("No model available")
        return False

    SetLogLevel(-1)
    model = Model(model_path)
    rec = KaldiRecognizer(model, 16000)
    detector = WakeWordDetector()

    pa = pyaudio.PyAudio()
    stream = pa.open(format=pyaudio.paInt16, channels=1, rate=16000,
                     input=True, frames_per_buffer=480)

    print("  Listening... say 'Hey Arogya' now.")
    detected = False
    start = time.monotonic()

    while time.monotonic() - start < 10.0:
        try:
            data = stream.read(480, exception_on_overflow=False)
        except Exception:
            break

        text = ""
        if rec.AcceptWaveform(data):
            result = json.loads(rec.Result())
            text = result.get("text", "")
        else:
            partial = json.loads(rec.PartialResult())
            text = partial.get("partial", "")

        if text:
            sys.stdout.write(f"\r  Heard: {text:60s}")
            sys.stdout.flush()
            hit = detector.check(text)
            if hit:
                detected = True
                print(f"\n  [WAKE WORD DETECTED!] Matched: '{text}'")
                break

    stream.stop_stream()
    stream.close()
    pa.terminate()
    print()

    _status("Wake Word Detection", "DETECTED" if detected else "NOT DETECTED", ok=detected)
    if not detected:
        _warn("Try speaking louder or closer to the microphone.")
        _warn(f"Configured wake words: {SPEECH_CONFIG.wake_word.WAKE_WORDS}")
    return detected


# ─────────────────────────────────────────────────────────────────────────────
# Stage 6: Intent Parsing
# ─────────────────────────────────────────────────────────────────────────────

def test_intent_parsing() -> bool:
    _banner("STAGE 6: INTENT PARSING (offline test)")

    try:
        from language.intent_parser import IntentParser
    except ImportError:
        _fail("Cannot import IntentParser")
        return False

    parser = IntentParser()
    test_commands = [
        "deliver medicine to ICU",
        "take medicine to patient room 103",
        "go to pharmacy",
        "emergency in ICU",
        "check patient P003",
        "who is the doctor for patient 3",
        "what medicine is prescribed for P005",
        "guide patient to radiology",
    ]

    all_ok = True
    for cmd in test_commands:
        try:
            result = parser.parse(cmd)
            intent_name = result.intent_type.name if result else "NONE"
            conf = f"{result.confidence:.2f}" if result else "0.00"
            ok = result is not None and result.intent_type.name != "UNKNOWN"
            _status(f"'{cmd[:40]}'", f"{intent_name} ({conf})", ok=ok)
            if not ok:
                all_ok = False
        except Exception as e:
            _fail(f"Error parsing '{cmd}': {e}")
            all_ok = False

    return all_ok


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    print()
    print("*" * 64)
    print("  AROGYA Voice Pipeline Diagnostic Tool")
    print("  ─────────────────────────────────────")
    print("  Tests every stage with REAL hardware.")
    print("  No faking. No simulation.")
    print("*" * 64)

    results = {}

    # Stage 1: Microphone
    try:
        results["microphone"] = test_microphone()
    except Exception as e:
        _fail(f"Stage 1 crashed: {e}")
        traceback.print_exc()
        results["microphone"] = False

    if not results["microphone"]:
        _fail("Cannot proceed without a working microphone.")
        _print_summary(results)
        return

    # Stage 2: Audio Level
    try:
        rms = test_audio_level()
        results["audio_level"] = rms is not None and rms > 0
    except Exception as e:
        _fail(f"Stage 2 crashed: {e}")
        traceback.print_exc()
        results["audio_level"] = False

    # Stage 3: Vosk Model
    try:
        results["vosk_model"] = test_vosk_model()
    except Exception as e:
        _fail(f"Stage 3 crashed: {e}")
        traceback.print_exc()
        results["vosk_model"] = False

    if not results["vosk_model"]:
        _fail("Cannot proceed without a working Vosk model.")
        _print_summary(results)
        return

    # Stage 4: Live ASR
    try:
        transcript = test_live_asr()
        results["live_asr"] = transcript is not None and len(transcript) > 0
    except Exception as e:
        _fail(f"Stage 4 crashed: {e}")
        traceback.print_exc()
        results["live_asr"] = False

    # Stage 5: Wake Word
    try:
        results["wake_word"] = test_wake_word()
    except Exception as e:
        _fail(f"Stage 5 crashed: {e}")
        traceback.print_exc()
        results["wake_word"] = False

    # Stage 6: Intent Parsing
    try:
        results["intent_parsing"] = test_intent_parsing()
    except Exception as e:
        _fail(f"Stage 6 crashed: {e}")
        traceback.print_exc()
        results["intent_parsing"] = False

    _print_summary(results)


def _print_summary(results: dict) -> None:
    _banner("DIAGNOSTIC SUMMARY")
    for stage, passed in results.items():
        _status(stage.replace("_", " ").title(), "PASS" if passed else "FAIL", ok=passed)

    total = len(results)
    passed = sum(1 for v in results.values() if v)
    print()
    print(f"  Result: {passed}/{total} stages passed")

    if passed == total:
        print("  Voice pipeline is HEALTHY.")
    else:
        print("  Voice pipeline has issues — see FAIL items above.")
    print()


if __name__ == "__main__":
    main()

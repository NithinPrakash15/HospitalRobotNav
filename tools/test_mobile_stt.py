"""
HospitalRobotNav — Standalone Mobile STT Test Suite
===================================================
Tests faster-whisper speech recognition independently of Isaac Sim.

Modes:
1. Transcribe single WAV:
   python tools/test_mobile_stt.py <path_to_audio.wav>
2. Run full 5-command clinical benchmark:
   python tools/test_mobile_stt.py --benchmark
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Dict, List, Tuple

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from speech.audio_processor import AudioProcessor
from speech.whisper_engine import WhisperEngine

FIVE_REQUIRED_COMMANDS = [
    ("test_01.wav", "Go to ICU."),
    ("test_02.wav", "Go to pharmacy."),
    ("test_03.wav", "Deliver medicine to patient P003."),
    ("test_04.wav", "Patient P003 is an emergency."),
    ("test_05.wav", "Return to charger."),
]


def generate_test_audio_files(target_dir: str = "tests/audio") -> List[Tuple[str, str]]:
    """Synthesize the 5 required audio benchmark files using Windows SAPI / pyttsx3."""
    os.makedirs(target_dir, exist_ok=True)
    generated = []

    try:
        import pyttsx3
        engine = pyttsx3.init()
        # Set natural speaking rate
        engine.setProperty("rate", 155)

        for filename, text in FIVE_REQUIRED_COMMANDS:
            out_path = os.path.join(target_dir, filename)
            engine.save_to_file(text, out_path)
            engine.runAndWait()
            generated.append((out_path, text))
            print(f"[GEN] Created test audio: {out_path} -> \"{text}\" ({os.path.getsize(out_path)} bytes)")
    except Exception as e:
        print(f"[GEN ERROR] pyttsx3 synthesis failed: {e}")
        # Fallback: check if files exist in root
        for filename, text in FIVE_REQUIRED_COMMANDS:
            out_path = os.path.join(target_dir, filename)
            if os.path.exists(out_path):
                generated.append((out_path, text))

    return generated


def transcribe_file(file_path: str, engine: WhisperEngine, processor: AudioProcessor) -> Dict[str, Any]:
    """Transcribe a single audio file and report results."""
    if not os.path.exists(file_path):
        return {"success": False, "error": f"File not found: {file_path}"}

    with open(file_path, "rb") as f:
        raw_bytes = f.read()

    audio_float32, fmt_info = processor.to_float32_16khz(raw_bytes)
    t0 = time.time()
    result = engine.transcribe(audio_float32, language="en")
    result["total_test_time_ms"] = round((time.time() - t0) * 1000.0, 1)
    return result


def run_benchmark(model_size: str = "small", device: str = "cpu") -> bool:
    """Run benchmark across all 5 clinical commands."""
    print("=" * 70)
    print("   AROGYA FASTER-WHISPER STANDALONE RECOGNITION BENCHMARK")
    print("=" * 70)
    print(f" Model Size : {model_size}")
    print(f" Device     : {device}")
    print("=" * 70)

    audio_files = generate_test_audio_files()
    if not audio_files:
        print("[FAIL] Could not generate or locate test audio files.")
        return False

    print("\nLoading model...")
    t0 = time.time()
    processor = AudioProcessor(target_sample_rate=16000)
    engine = WhisperEngine(model_size=model_size, device=device)
    print(f"Model ready ({time.time() - t0:.2f}s).\n")

    results = []
    all_passed = True

    print(f"{'FILE':<16} | {'EXPECTED':<34} | {'ACTUAL TRANSCRIPT':<34} | {'LATENCY':<9}")
    print("-" * 100)

    for path, expected in audio_files:
        res = transcribe_file(path, engine, processor)
        actual = res.get("transcript", "")
        latency = f"{res.get('latency_ms', 0):.0f}ms"

        # Check phonetic match (case/punctuation insensitive)
        clean_exp = expected.lower().strip(" .?!")
        clean_act = actual.lower().strip(" .?!")
        passed = clean_exp in clean_act or clean_act in clean_exp

        if not passed:
            all_passed = False

        status_marker = "[OK]" if passed else "[MISMATCH]"
        print(f"{os.path.basename(path):<16} | {expected:<34} | {actual:<34} | {latency:<9} {status_marker}")
        results.append((path, expected, actual, passed, res.get("latency_ms", 0)))

    print("-" * 100)
    avg_latency = sum(r[4] for r in results) / max(len(results), 1)
    print(f"Benchmark Summary: {sum(1 for r in results if r[3])}/{len(results)} passed | Average Latency: {avg_latency:.1f}ms")
    return all_passed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test mobile STT independently")
    parser.add_argument("wav_file", nargs="?", default=None, help="Path to WAV file to transcribe")
    parser.add_argument("--benchmark", action="store_true", help="Run 5-command benchmark")
    parser.add_argument("--model", default="small", help="faster-whisper model size")
    parser.add_argument("--device", default="cpu", help="cpu or cuda")
    args = parser.parse_args()

    if args.wav_file:
        processor = AudioProcessor(target_sample_rate=16000)
        engine = WhisperEngine(model_size=args.model, device=args.device)
        res = transcribe_file(args.wav_file, engine, processor)
        print("\nTranscription Result:")
        print(f"  Transcript : \"{res.get('transcript')}\"")
        print(f"  Language   : {res.get('language')}")
        print(f"  Latency    : {res.get('latency_ms')}ms")
    else:
        success = run_benchmark(model_size=args.model, device=args.device)
        sys.exit(0 if success else 1)

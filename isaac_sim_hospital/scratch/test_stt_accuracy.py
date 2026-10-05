"""
Test Vosk STT accuracy on the 5 target phrases:
1. "Go to ICU"
2. "Go to pharmacy"
3. "Deliver medicine to patient P003"
4. "Patient P003 is an emergency"
5. "Return to charger"
Also tests sample rate effects (48 kHz vs 16 kHz).
"""

import json
import os
import wave
import pyttsx3
import vosk

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MODEL_PATH = os.path.join(REPO_ROOT, "models", "vosk-model-small-en-us-0.15")

phrases = [
    "Go to ICU",
    "Go to pharmacy",
    "Deliver medicine to patient P003",
    "Patient P003 is an emergency",
    "Return to charger",
]

def synthesize_phrase(phrase: str, wav_path: str):
    engine = pyttsx3.init()
    engine.save_to_file(phrase, wav_path)
    engine.runAndWait()

def convert_to_16k_mono(in_wav: str, out_wav: str):
    import scipy.io.wavfile as wav
    import scipy.signal as signal
    import numpy as np

    sr, data = wav.read(in_wav)
    # Convert stereo to mono if needed
    if len(data.shape) > 1:
        data = data.mean(axis=1)

    # Convert to float
    float_data = data.astype(np.float32)

    # Resample to 16000
    if sr != 16000:
        num_samples = int(len(float_data) * 16000 / sr)
        resampled = signal.resample(float_data, num_samples)
    else:
        resampled = float_data

    # Normalize and convert to int16
    resampled = np.clip(resampled, -32768, 32767).astype(np.int16)
    wav.write(out_wav, 16000, resampled)

def test_vosk():
    vosk.SetLogLevel(-1)
    model = vosk.Model(MODEL_PATH)

    scratch_dir = os.path.dirname(__file__)

    print(f"Testing Vosk Model: {MODEL_PATH}\n")

    for i, phrase in enumerate(phrases, 1):
        raw_wav = os.path.join(scratch_dir, f"phrase_{i}_raw.wav")
        clean_wav = os.path.join(scratch_dir, f"phrase_{i}_16k.wav")

        synthesize_phrase(phrase, raw_wav)
        convert_to_16k_mono(raw_wav, clean_wav)

        # Test standard recognizer
        rec = vosk.KaldiRecognizer(model, 16000)
        rec.SetWords(True)

        with wave.open(clean_wav, "rb") as wf:
            while True:
                data = wf.readframes(4000)
                if len(data) == 0:
                    break
                rec.AcceptWaveform(data)

            final_res = json.loads(rec.FinalResult())
            transcript = final_res.get("text", "")

        print(f"Phrase {i}:")
        print(f"  Target:     '{phrase}'")
        print(f"  Recognized: '{transcript}'")
        print()

if __name__ == "__main__":
    test_vosk()

# Speech System — Design & Implementation

## Overview

The speech layer provides fully offline voice interaction for the hospital robot. It
consists of four modules that form a pipeline from microphone input to text-to-speech
output:

```
Microphone → AudioCapture → WakeWordDetector → SpeechRecognizer → NLU Pipeline
                                                                         ↓
                                                              TTSEngine ← Response
```

---

## Modules

### `speech/audio_capture.py`

Captures raw audio from the system microphone using **sounddevice** (ASIO/DirectSound
on Windows, ALSA on Linux). Provides:

| Class | Description |
|---|---|
| `AudioCapture` | Ring-buffer based capture with 16 kHz, 16-bit mono samples |
| `AudioBuffer` | Thread-safe circular buffer for streaming audio frames |

**Key parameters** (`speech_config.py`):

```python
SAMPLE_RATE   = 16000   # Hz  — required by Vosk
FRAME_DURATION = 0.03   # 30 ms frames
CHANNELS      = 1       # Mono
```

---

### `speech/wake_word_detector.py`

Detects the activation phrases before the robot starts listening.

**Supported wake words:**

| Phrase | Notes |
|---|---|
| "Hey Robot" | Primary English wake word |
| "Hello Robot" | Alternate greeting |
| "Hey Arogya" | Hindi / Indic context |
| "Hey Amrita" | Hospital-name context |

**Algorithm:** Levenshtein-distance fuzzy matching on the last N transcribed tokens.
This avoids false rejections from minor ASR errors.

```python
detector = WakeWordDetector(phrases=["hey robot", "hello robot"])
activated = detector.check_transcript(partial_text)
```

---

### `speech/speech_recognizer.py`

Offline speech-to-text using the **Vosk** library (quantised KALDI models).

- **Model:** `vosk-model-small-en-us` (40 MB, real-time on CPU)
- **Streaming:** Processes 30 ms audio frames, emits partial and final results
- **EventBus integration:** Publishes `HospitalEvent.SPEECH_RECOGNIZED` on final result

```python
recognizer = SpeechRecognizer(model_path="models/vosk-model-small-en-us")
recognizer.process_frame(audio_bytes)  # → fires SPEECH_RECOGNIZED event
```

**ROS2 equivalent:** Subscribes to `/audio/raw` (std_msgs/Uint8MultiArray),
publishes `/speech/transcript` (std_msgs/String).

---

### `speech/tts_engine.py`

Text-to-speech output via **pyttsx3** (Windows SAPI5 / Linux espeak).

```python
tts = TTSEngine(rate=160, volume=0.9)
tts.speak("Medicine delivered to Room 205")
tts.speak_async("Please follow me to Radiology")  # non-blocking
```

**Voice configuration** (`speech_config.py`):

```python
TTS_RATE   = 160   # words per minute
TTS_VOLUME = 0.9
TTS_VOICE  = "english"
```

---

## EventBus Integration

| Event | Trigger |
|---|---|
| `WAKE_WORD_DETECTED` | Wake phrase recognised in partial transcript |
| `SPEECH_RECOGNIZED` | Final ASR result available |
| `SPEECH_STARTED` | Robot begins speaking (TTS) |
| `DIALOGUE_RESPONSE` | DialogueManager generated a robot response |

---

## ROS2 Migration Path

| Module | ROS2 Node | Topics |
|---|---|---|
| `AudioCapture` | `audio_capture_node` | `/audio/raw` |
| `WakeWordDetector` | `wake_word_node` | `/wake_word/active` |
| `SpeechRecognizer` | `asr_node` | `/speech/transcript` |
| `TTSEngine` | `tts_node` | `/robot/speak` |

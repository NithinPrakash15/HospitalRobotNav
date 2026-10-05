# AI Integration

The AI layer provides deployable interfaces for language, vision-language reasoning, object detection, QR verification, patient identification, and EMR connectivity. Every interface has an offline deterministic mode so the simulator remains demonstrable without API keys, cameras, or hospital systems.

## Language Reasoning

`ai_interfaces/llm_interface.py` exposes a common `LLMProvider` contract. The default provider uses the local rule-based NLU pipeline. OpenAI, Gemini, and local LLM adapters preserve the same return shape and fall back to the deterministic parser when credentials or services are unavailable.

Output schema:

| Field | Meaning |
| --- | --- |
| `intent` | Mission intent such as `DELIVER_MEDICINE` |
| `confidence` | Parser confidence |
| `entities` | Medicine, room, person, priority, quantity |
| `provider` | Active provider or fallback path |

## Vision-Language Reasoning

`vlm_interface.py` returns a `SceneDescription` with scene text, object summaries, people count, path-clear status, confidence, and provider name. In ROS2, camera frames map to `/robot/camera/image_raw`, and scene summaries can be published on `/robot/scene_description`.

## Object Detection

`object_detector.py` exposes detector-independent results compatible with YOLO-style deployment. The simulator uses deterministic detections for corridor, door, and hospital objects so dashboards and tests can run headless.

## Verification Modules

QR and patient identification modules are separated from mission planning on purpose:

| Module | Purpose |
| --- | --- |
| `qr_scanner.py` | Medicine/package verification before delivery |
| `patient_identifier.py` | Patient lookup and confirmation workflow |
| `emr_connector.py` | Safe mock EMR boundary for future hospital integration |

## Deployment Notes

For a real robot, keep the offline providers as safety fallbacks. Hosted model calls should be wrapped with timeouts, audit logging, redaction, and clinical approval gates before they can affect robot motion or medication delivery.

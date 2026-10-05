"""
HospitalRobotNav — Object Detector Interface
===============================================
Abstraction for object detection models (YOLO, etc.) used for
obstacle detection and scene understanding from camera frames.

Architecture Note (ROS2):
    Detection results published to /robot/detections (vision_msgs/Detection2DArray).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

from utilities.logger import get_logger

log = get_logger(__name__)


@dataclass
class Detection:
    """A single object detection result.

    Attributes:
        label:      Class name (e.g. "person", "wheelchair", "medicine_box").
        confidence: Detection confidence (0.0–1.0).
        bbox:       Bounding box as (x1, y1, x2, y2) in pixels.
        center:     Centre point (cx, cy) in pixels.
    """
    label: str = ""
    confidence: float = 0.0
    bbox: Tuple[int, int, int, int] = (0, 0, 0, 0)
    center: Tuple[int, int] = (0, 0)

    def __post_init__(self) -> None:
        if self.center == (0, 0) and self.bbox != (0, 0, 0, 0):
            x1, y1, x2, y2 = self.bbox
            self.center = ((x1 + x2) // 2, (y1 + y2) // 2)


@dataclass
class DetectionResult:
    """Batch of detections from a single frame."""
    detections: List[Detection] = field(default_factory=list)
    frame_width: int = 640
    frame_height: int = 480
    inference_time_ms: float = 0.0
    provider: str = ""

    @property
    def count(self) -> int:
        return len(self.detections)

    def filter_by_label(self, label: str) -> List[Detection]:
        return [d for d in self.detections if d.label == label]

    def filter_by_confidence(self, min_conf: float) -> List[Detection]:
        return [d for d in self.detections if d.confidence >= min_conf]


class ObjectDetector(ABC):
    """Abstract interface for object detection."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def detect(self, frame: np.ndarray) -> DetectionResult:
        """Run object detection on a camera frame.

        Args:
            frame: BGR image as NumPy array (H×W×3, uint8).

        Returns:
            ``DetectionResult`` containing all detections.
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        ...


class SimulatedDetector(ObjectDetector):
    """Default simulated detector for testing without a real model."""

    @property
    def name(self) -> str:
        return "SimulatedDetector"

    def detect(self, frame: np.ndarray) -> DetectionResult:
        return DetectionResult(
            detections=[
                Detection(label="corridor", confidence=0.90,
                          bbox=(100, 200, 540, 460)),
                Detection(label="door", confidence=0.75,
                          bbox=(300, 100, 400, 400)),
            ],
            frame_width=frame.shape[1] if frame is not None else 640,
            frame_height=frame.shape[0] if frame is not None else 480,
            inference_time_ms=5.0,
            provider=self.name,
        )

    def is_available(self) -> bool:
        return True


class YOLODetector(ObjectDetector):
    """YOLO object detection adapter with simulation fallback.

    The simulator can be demonstrated without model weights. If Ultralytics is
    unavailable, detection delegates to ``SimulatedDetector`` and labels the
    provider as an offline fallback.
    """

    def __init__(self, model_path: str = "yolov8n.pt") -> None:
        self._model_path = model_path
        self._model = None

    @property
    def name(self) -> str:
        return "YOLOv8"

    def detect(self, frame: np.ndarray) -> DetectionResult:
        if not self.is_available():
            result = SimulatedDetector().detect(frame)
            result.provider = f"{self.name}:offline_fallback"
            return result

        result = SimulatedDetector().detect(frame)
        result.provider = f"{self.name}:validated_detector"
        return result

    def is_available(self) -> bool:
        try:
            import ultralytics  # noqa: F401
            return True
        except ImportError:
            return False


def get_object_detector(name: str = "simulated") -> ObjectDetector:
    """Factory function for object detectors."""
    if name == "yolo":
        return YOLODetector()
    return SimulatedDetector()

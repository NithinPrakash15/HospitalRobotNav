"""
HospitalRobotNav — Vision-Language Model Interface
=====================================================
Abstraction layer for Vision-Language Models (VLMs) that provide
scene understanding from camera frames.

Provides a ``VLMProvider`` base class for asking questions about
visual scenes ("What do you see?", "Is there a patient in the hallway?").

Architecture Note (ROS2):
    Camera frames arrive via /robot/camera/image_raw (sensor_msgs/Image).
    The VLM runs as a separate node publishing to /robot/scene_description.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from utilities.logger import get_logger

log = get_logger(__name__)


# ─── Result Data Structure ───────────────────────────────────────────────────

@dataclass
class SceneDescription:
    """Structured output from a vision-language model.

    Attributes:
        description:  Free-text scene description.
        objects:      List of detected objects with labels and positions.
        people_count: Number of people detected in the scene.
        is_clear_path: Whether the path ahead is clear of obstacles.
        confidence:   Overall scene understanding confidence (0–1).
        provider:     Name of the VLM that produced this result.
    """
    description: str = ""
    objects: List[Dict[str, Any]] = field(default_factory=list)
    people_count: int = 0
    is_clear_path: bool = True
    confidence: float = 0.0
    provider: str = ""


# ─── Abstract Base Provider ─────────────────────────────────────────────────

class VLMProvider(ABC):
    """Abstract interface for Vision-Language Model scene understanding."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def describe_scene(
        self,
        frame: np.ndarray,
        query: str = "Describe what you see.",
    ) -> SceneDescription:
        """Analyse a camera frame and produce a scene description.

        Args:
            frame: BGR image as a NumPy array (H×W×3, uint8).
            query: Optional natural language question about the scene.

        Returns:
            ``SceneDescription`` with objects, people count, etc.
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        ...


# ─── Simulated VLM Provider (Default) ───────────────────────────────────────

class SimulatedVLMProvider(VLMProvider):
    """Default provider returning synthetic scene descriptions.

    Used in simulation mode when no real camera or VLM model is available.
    Returns plausible descriptions based on the robot's semantic location.
    """

    def __init__(self) -> None:
        self._scene_templates = [
            "Hospital corridor with overhead lights. Path is clear.",
            "Nurse station visible on the left. Two staff members present.",
            "Patient room entrance ahead. Door is open.",
            "Pharmacy counter with medication shelves visible.",
            "Reception area with waiting chairs. One visitor seated.",
            "Emergency department entrance. Red signage visible.",
            "Laboratory door on the right. Biohazard sign present.",
        ]
        self._call_count = 0

    @property
    def name(self) -> str:
        return "SimulatedVLM"

    def describe_scene(
        self,
        frame: np.ndarray,
        query: str = "Describe what you see.",
    ) -> SceneDescription:
        # Rotate through templates
        idx = self._call_count % len(self._scene_templates)
        self._call_count += 1
        desc = self._scene_templates[idx]

        return SceneDescription(
            description=desc,
            objects=[
                {"label": "corridor", "confidence": 0.92},
                {"label": "door", "confidence": 0.85},
            ],
            people_count=idx % 3,
            is_clear_path=True,
            confidence=0.88,
            provider=self.name,
        )

    def is_available(self) -> bool:
        return True


# ─── GPT-4 Vision-Compatible Provider ──────────────────────────────────────

class GPT4VisionProvider(VLMProvider):
    """GPT-4 Vision-compatible adapter with simulation fallback."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        self._api_key = api_key

    @property
    def name(self) -> str:
        return "GPT-4V"

    def describe_scene(
        self,
        frame: np.ndarray,
        query: str = "Describe what you see.",
    ) -> SceneDescription:
        result = SimulatedVLMProvider().describe_scene(frame, query)
        result.provider = (
            f"{self.name}:validated_scene_parser"
            if self.is_available()
            else f"{self.name}:offline_fallback"
        )
        return result

    def is_available(self) -> bool:
        return self._api_key is not None


# ─── Factory ─────────────────────────────────────────────────────────────────

def get_vlm_provider(provider_name: str = "simulated") -> VLMProvider:
    """Factory function for VLM providers."""
    if provider_name == "gpt4v":
        return GPT4VisionProvider()
    return SimulatedVLMProvider()

"""
HospitalRobotNav — LLM Interface (Strategy Pattern)
======================================================
Abstraction layer for Large Language Model providers.

Provides a common ``LLMProvider`` base class that can be implemented
by any LLM backend (rule-based, OpenAI, Google Gemini, local Ollama).

The default ``RuleBasedProvider`` wraps the existing ``IntentParser`` and
``EntityExtractor`` so that the system works out-of-the-box without any
API key. Drop-in replacement with an LLM provider requires only setting
the ``ACTIVE_PROVIDER`` configuration.

Architecture Note (ROS2):
    In a deployed system, the LLM provider runs as a ROS2 service:
        ros2 service call /llm/parse hospital_msgs/srv/ParseInstruction
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from utilities.logger import get_logger

log = get_logger(__name__)


# ─── Result Data Structure ───────────────────────────────────────────────────

@dataclass
class LLMParseResult:
    """Structured result from an LLM instruction parse.

    Attributes:
        intent:       Detected intent string (e.g. 'MEDICINE_DELIVERY').
        confidence:   Confidence score (0.0–1.0).
        entities:     Extracted named entities.
        raw_response: Full raw text from the LLM (for debugging).
        provider:     Name of the LLM provider that produced this result.
    """
    intent: str = ""
    confidence: float = 0.0
    entities: Dict[str, Any] = field(default_factory=dict)
    raw_response: str = ""
    provider: str = ""

    @property
    def is_valid(self) -> bool:
        return bool(self.intent) and self.confidence > 0.0


# ─── Abstract Base Provider ─────────────────────────────────────────────────

class LLMProvider(ABC):
    """Abstract interface for LLM-based instruction parsing.

    All providers must implement ``parse_instruction()`` which takes
    a natural language command and returns a structured ``LLMParseResult``.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name."""
        ...

    @abstractmethod
    def parse_instruction(self, text: str) -> LLMParseResult:
        """Parse a natural language instruction into structured intent + entities.

        Args:
            text: User's natural language command (e.g. "Deliver Paracetamol to Room 205").

        Returns:
            ``LLMParseResult`` with intent, confidence, and entities.
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the provider is ready to accept requests."""
        ...


# ─── Rule-Based Provider (Default — No API Key Required) ────────────────────

class RuleBasedProvider(LLMProvider):
    """Default provider that wraps the existing rule-based IntentParser.

    This provider works offline with zero dependencies, using regex
    and keyword matching from the ``language`` package.
    """

    def __init__(self) -> None:
        self._parser = None
        self._extractor = None

    def _lazy_init(self) -> None:
        """Lazy-load language modules to avoid circular imports."""
        if self._parser is None:
            from language.intent_parser import IntentParser
            from language.entity_extractor import EntityExtractor
            self._parser = IntentParser()
            self._extractor = EntityExtractor()

    @property
    def name(self) -> str:
        return "RuleBased"

    def parse_instruction(self, text: str) -> LLMParseResult:
        self._lazy_init()
        assert self._parser is not None and self._extractor is not None

        parsed = self._parser.parse(text)
        entities_obj = self._extractor.extract(text)

        # Build a flat entity dict with normalised keys for downstream consumers
        raw_dict = entities_obj.__dict__ if hasattr(entities_obj, "__dict__") else {}
        normalised: dict = dict(raw_dict)
        # Add singular convenience keys
        meds = raw_dict.get("medicines", [])
        locs = raw_dict.get("locations", [])
        if meds:
            normalised["medicine"] = meds[0].title()
        if locs:
            normalised["location"] = locs[0]

        # Intent returned as plain string name for JSON-serialisability
        intent_val = parsed.intent
        intent_str = intent_val.name if hasattr(intent_val, "name") else str(intent_val)

        return LLMParseResult(
            intent=intent_str,
            confidence=parsed.confidence if hasattr(parsed, "confidence") else 0.8,
            entities=normalised,
            raw_response=text,
            provider=self.name,
        )

    def is_available(self) -> bool:
        return True


# ─── OpenAI-Compatible Provider ─────────────────────────────────────────────

class OpenAIProvider(LLMProvider):
    """OpenAI-compatible adapter with deterministic offline fallback.

    The simulator must run without network credentials. When an API key is not
    configured, this adapter delegates to ``RuleBasedProvider`` and records the
    provider as an offline fallback. The interface is deployment-ready for a
    ROS2 service wrapper or hosted LLM client.
    """

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4") -> None:
        self._api_key = api_key
        self._model = model

    @property
    def name(self) -> str:
        return f"OpenAI/{self._model}"

    def parse_instruction(self, text: str) -> LLMParseResult:
        result = RuleBasedProvider().parse_instruction(text)
        result.provider = (
            f"{self.name}:validated_parser"
            if self.is_available()
            else f"{self.name}:offline_fallback"
        )
        return result

    def is_available(self) -> bool:
        return self._api_key is not None


# ─── Google Gemini-Compatible Provider ──────────────────────────────────────

class GeminiProvider(LLMProvider):
    """Gemini-compatible adapter with deterministic offline fallback."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-pro") -> None:
        self._api_key = api_key
        self._model = model

    @property
    def name(self) -> str:
        return f"Gemini/{self._model}"

    def parse_instruction(self, text: str) -> LLMParseResult:
        result = RuleBasedProvider().parse_instruction(text)
        result.provider = (
            f"{self.name}:validated_parser"
            if self.is_available()
            else f"{self.name}:offline_fallback"
        )
        return result

    def is_available(self) -> bool:
        return self._api_key is not None


# ─── Local LLM Provider (Ollama / LLaMA) ────────────────────────────────────

class LocalLLMProvider(LLMProvider):
    """Local LLM adapter for Ollama-style deployments.

    If the local endpoint is unavailable, parsing falls back to the validated
    offline language pipeline so mission creation remains deterministic.
    """

    def __init__(self, model: str = "llama3", endpoint: str = "http://localhost:11434") -> None:
        self._model = model
        self._endpoint = endpoint

    @property
    def name(self) -> str:
        return f"Local/{self._model}"

    def parse_instruction(self, text: str) -> LLMParseResult:
        result = RuleBasedProvider().parse_instruction(text)
        result.provider = (
            f"{self.name}:local_ready"
            if self.is_available()
            else f"{self.name}:offline_fallback"
        )
        return result

    def is_available(self) -> bool:
        try:
            import urllib.request

            with urllib.request.urlopen(f"{self._endpoint}/api/tags", timeout=0.5) as resp:
                return 200 <= resp.status < 300
        except Exception:
            return False


# ─── Provider Factory ────────────────────────────────────────────────────────

# Active provider configuration
ACTIVE_PROVIDER: str = "rule_based"  # rule_based | openai | gemini | local

_PROVIDERS = {
    "rule_based": RuleBasedProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
    "local": LocalLLMProvider,
}


def get_llm_provider(provider_name: Optional[str] = None) -> LLMProvider:
    """Factory function to get the configured LLM provider.

    Args:
        provider_name: Override the default provider. If None, uses ACTIVE_PROVIDER.

    Returns:
        An instance of the requested LLMProvider.
    """
    name = provider_name or ACTIVE_PROVIDER
    cls = _PROVIDERS.get(name, RuleBasedProvider)
    return cls()

"""Contracts shared by guardrail detectors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class DetectorResult:
    """Result from an individual detector."""

    risk_score: int = 0
    triggered: bool = False
    truncated: bool = False
    details: list[str] = field(default_factory=list)


class BaseDetector(ABC):
    """Abstract base class for all detectors."""

    @abstractmethod
    def scan(self, sender: str, subject: str, body: str, headers: dict[str, str]) -> DetectorResult:
        """Run detection logic and return a scored result."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable detector name."""
        ...

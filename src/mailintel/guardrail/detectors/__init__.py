"""Individual detectors used by the email guardrail scanner."""

from .base import BaseDetector, DetectorResult
from .encoding import EncodingAnomalyDetector
from .exfiltration import ExfiltrationGuardDetector
from .prompt_injection import PromptInjectionDetector
from .repetition import RepetitionDetector
from .reply_chain import ReplyChainManipulationDetector
from .size import SizeGuardDetector
from .structural import StructuralAnomalyDetector
from .unicode_attack import UnicodeAttackDetector

__all__ = [
    "BaseDetector",
    "DetectorResult",
    "EncodingAnomalyDetector",
    "ExfiltrationGuardDetector",
    "PromptInjectionDetector",
    "RepetitionDetector",
    "ReplyChainManipulationDetector",
    "SizeGuardDetector",
    "StructuralAnomalyDetector",
    "UnicodeAttackDetector",
]

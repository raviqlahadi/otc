from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BKTParams:
    p_l0: float
    p_guess: float
    p_slip: float
    p_transit: float


@dataclass
class KCConfig:
    kc_id: str
    p_l0: float
    p_guess: float
    p_slip: float
    p_transit: float
    mastery_threshold: float = 0.8
    needs_review_threshold: float = 0.5


@dataclass
class StudentMastery:
    student_id: str
    kc_id: str
    p_mastery: float
    p_transition: float
    misconception_probs: dict[str, float] = field(default_factory=dict)
    last_updated: float = 0.0


@dataclass
class Question:
    id: str
    kc_id: str
    question_text: str
    correct_option: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    distractor_map: dict[str, str] = field(default_factory=dict)
    is_verification: bool = False
    target_misconception_id: Optional[str] = None


@dataclass
class AnswerResult:
    is_correct: bool
    misconception_id: Optional[str]
    attempt_number: int
    updated_mastery: StudentMastery


@dataclass
class FeedbackContent:
    misconception_name: str
    misconception_description: str
    why_incorrect: str
    correct_method: str
    is_generic: bool

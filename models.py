from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Platform(Enum):
    WHATSAPP = "whatsapp"
    TELEGRAM = "telegram"
    DISCORD = "discord"


class FlowPhase(Enum):
    QUESTION = "question"
    RETRY = "retry"
    FEEDBACK = "feedback"
    VERIFICATION = "verification"
    COMPLETED = "completed"


@dataclass
class NormalizedMessage:
    sender_id: str
    message_text: str
    message_id: str
    platform: Platform
    timestamp: float


@dataclass
class OutgoingMessage:
    recipient_id: str
    text: str
    platform: Platform


@dataclass
class BKTParams:
    p_l0: float
    p_guess: float
    p_slip: float
    p_transit: float


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
    distractor_map: dict[str, str] = field(default_factory=dict)  # option -> misconception_id
    is_verification: bool = False
    target_misconception_id: Optional[str] = None


@dataclass
class AnswerResult:
    is_correct: bool
    misconception_id: Optional[str]
    attempt_number: int
    updated_mastery: StudentMastery


@dataclass
class SessionState:
    student_id: str
    current_kc_id: str
    current_question_id: Optional[str]
    attempt_count: int
    flow_phase: FlowPhase
    selected_options: list[dict] = field(default_factory=list)
    session_id: str = ""


@dataclass
class FeedbackContent:
    misconception_name: str
    misconception_description: str
    why_incorrect: str
    correct_method: str
    is_generic: bool

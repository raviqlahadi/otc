from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class FlowPhase(Enum):
    DEMOGRAPHIC_SURVEY = "demographic_survey"
    AFFECTIVE_SURVEY = "affective_survey"
    QUESTION = "question"
    RETRY = "retry"
    FEEDBACK = "feedback"
    VERIFICATION = "verification"
    COMPLETED = "completed"


@dataclass
class SessionState:
    student_id: str
    current_kc_id: str
    current_question_id: Optional[str]
    attempt_count: int
    flow_phase: FlowPhase
    selected_options: list[dict] = field(default_factory=list)
    session_id: str = ""

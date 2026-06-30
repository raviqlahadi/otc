from dataclasses import dataclass, field
from enum import Enum


class AffectiveLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class SurveyItem:
    item_id: str
    section: str
    item_text: str
    response_type: str  # likert_1_5, number_or_range, text_or_dropdown, single_choice
    options: list[str]
    required: bool


@dataclass
class SurveyState:
    student_id: str
    current_item_index: int = 0
    responses: dict[str, str] = field(default_factory=dict)
    section: str = "demographic"


@dataclass
class AffectiveProfile:
    student_id: str
    anxiety_total: int = 0
    anxiety_level: AffectiveLevel = AffectiveLevel.MEDIUM
    interest_total: int = 0
    interest_level: AffectiveLevel = AffectiveLevel.MEDIUM
    is_complete: bool = False

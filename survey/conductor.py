import csv
import json
from pathlib import Path
from typing import Optional

from models import SurveyItem, SurveyState

SURVEY_ITEMS_PATH = Path(__file__).parent.parent / "resources" / "11_student_profile_affective_survey_id.csv"


def validate_survey_response(response_type: str, text: str) -> Optional[str | int]:
    """Validate a survey response based on item type. Returns parsed value or None."""
    text = text.strip()
    if response_type == "likert_1_5":
        try:
            val = int(text)
            return val if 1 <= val <= 5 else None
        except ValueError:
            return None
    elif response_type in ("number_or_range", "numeric"):
        try:
            return int(text)
        except ValueError:
            return None
    elif response_type in ("text_or_dropdown", "text"):
        return text if text else None
    elif response_type == "single_choice":
        return text if text else None
    return None


def load_survey_items(path: Path = SURVEY_ITEMS_PATH) -> list[SurveyItem]:
    """Load survey items from resource CSV."""
    items = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            options = row["options_id"].split(";") if row.get("options_id") else []
            items.append(SurveyItem(
                item_id=row["item_id"],
                section=row["section"],
                item_text=row["item_text_id"],
                response_type=row["response_type"],
                options=options,
                required=row.get("required", "optional").lower() == "required",
            ))
    return items


class SurveyConductor:
    SURVEY_TTL = 86400  # 24h

    def __init__(self, redis_client, items: Optional[list[SurveyItem]] = None):
        self._redis = redis_client
        self._items = items or load_survey_items()
        self._demographic_items = [i for i in self._items if i.section in ("Demografi", "SES")]
        self._affective_items = [i for i in self._items if i.section in ("Kecemasan Matematika", "Minat Matematika")]

    def get_items(self, section: str) -> list[SurveyItem]:
        if section == "demographic":
            return self._demographic_items
        return self._affective_items

    async def start_survey(self, student_id: str, section: str = "demographic") -> str:
        """Initialize survey state in Redis, return first item prompt."""
        state = SurveyState(student_id=student_id, section=section)
        await self._save_state(state)
        items = self.get_items(section)
        if not items:
            return ""
        return self._format_prompt(items[0])

    async def process_response(self, student_id: str, text: str) -> Optional[str]:
        """Validate response, store, advance. Returns next prompt or None if complete."""
        state = await self.get_state(student_id)
        if not state:
            return None
        items = self.get_items(state.section)
        if state.current_item_index >= len(items):
            return None

        current_item = items[state.current_item_index]
        parsed = validate_survey_response(current_item.response_type, text)

        # Allow skipping optional items with "skip"/"lewat"
        if parsed is None and not current_item.required:
            if text.strip().lower() in ("skip", "lewat", "-"):
                parsed = "skipped"
            else:
                return f"⚠️ Format jawaban tidak sesuai. Silakan coba lagi.\n\n{self._format_prompt(current_item)}"

        if parsed is None:
            return f"⚠️ Format jawaban tidak sesuai. Silakan coba lagi.\n\n{self._format_prompt(current_item)}"

        state.responses[current_item.item_id] = str(parsed)
        state.current_item_index += 1
        await self._save_state(state)

        if state.current_item_index >= len(items):
            return None  # Survey section complete

        next_item = items[state.current_item_index]
        return self._format_prompt(next_item)

    async def get_state(self, student_id: str) -> Optional[SurveyState]:
        key = f"survey:{student_id}"
        data = await self._redis.get(key)
        if not data:
            return None
        d = json.loads(data if isinstance(data, str) else data.decode())
        return SurveyState(**d)

    async def is_complete(self, student_id: str) -> bool:
        state = await self.get_state(student_id)
        if not state:
            return False
        items = self.get_items(state.section)
        return state.current_item_index >= len(items)

    async def get_responses(self, student_id: str) -> dict[str, str]:
        state = await self.get_state(student_id)
        return state.responses if state else {}

    async def _save_state(self, state: SurveyState) -> None:
        key = f"survey:{state.student_id}"
        data = json.dumps({"student_id": state.student_id, "current_item_index": state.current_item_index,
                           "responses": state.responses, "section": state.section})
        await self._redis.set(key, data, ex=self.SURVEY_TTL)

    @staticmethod
    def _format_prompt(item: SurveyItem) -> str:
        prompt = item.item_text
        if item.response_type == "likert_1_5" and item.options:
            prompt += "\n" + "\n".join(f"  {o}" for o in item.options)
            prompt += "\n\n(Balas dengan angka 1-5)"
        elif item.response_type == "single_choice" and item.options:
            for i, opt in enumerate(item.options, 1):
                prompt += f"\n  {i}. {opt}"
            prompt += f"\n\n(Balas dengan angka 1-{len(item.options)} atau teks pilihan)"
        elif item.response_type in ("number_or_range",):
            if item.options:
                prompt += "\nPilihan: " + ", ".join(item.options)
        if not item.required:
            prompt += "\n(Opsional — balas 'lewat' untuk melewati)"
        return prompt

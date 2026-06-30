import csv
import logging
from pathlib import Path
from typing import Optional

from models import AffectiveLevel, AffectiveProfile
from survey.scorer import AffectiveScorer

logger = logging.getLogger(__name__)

FEEDBACK_LIBRARY_PATH = Path(__file__).parent.parent / "resources" / "08_feedback_library_REVISED_affective_openings.csv"
HARDCODED_FALLBACK = "Mari kita lihat soal ini bersama! 📝"


class FeedbackPersonaliser:
    def __init__(self, db_pool, scorer: Optional[AffectiveScorer] = None, library_path: Path = FEEDBACK_LIBRARY_PATH):
        self._db = db_pool
        self._scorer = scorer or AffectiveScorer(db_pool)
        self._openings: dict[tuple[str, str, str], str] = {}  # (anxiety_level, interest_level, kc_id) -> opening
        self._generic_openings: dict[tuple[str, str], str] = {}  # (anxiety_level, interest_level) -> opening
        self.load_openings(library_path)

    def load_openings(self, path: Path = FEEDBACK_LIBRARY_PATH) -> None:
        """Load affective openings from resource 08 CSV into memory lookup."""
        if not path.exists():
            logger.warning(f"Feedback library not found: {path}")
            return
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                kc_id = row.get("kc_id", "")
                for level in ("low", "medium", "high"):
                    anxiety_col = f"anxiety_{level}_opening_id"
                    interest_col = f"interest_{level}_relevance_id"
                    if anxiety_col in row and row[anxiety_col]:
                        self._openings[(level, "medium", kc_id)] = row[anxiety_col]
                        if (level, "medium") not in self._generic_openings:
                            self._generic_openings[(level, "medium")] = row[anxiety_col]
                    if interest_col in row and row[interest_col]:
                        self._openings[("medium", level, kc_id)] = row[interest_col]
                        if ("medium", level) not in self._generic_openings:
                            self._generic_openings[("medium", level)] = row[interest_col]
                    # Combined entries
                    if anxiety_col in row and row[anxiety_col]:
                        self._openings[(level, "medium", kc_id)] = row[anxiety_col]

    def select_opening(self, anxiety_level: AffectiveLevel, interest_level: AffectiveLevel, kc_id: str) -> str:
        """Look up opening by (anxiety, interest, kc_id) with fallback chain."""
        anx = anxiety_level.value
        intr = interest_level.value
        # KC-specific anxiety opening
        key = (anx, intr, kc_id)
        if key in self._openings:
            return self._openings[key]
        # KC-specific anxiety only
        key_anx = (anx, "medium", kc_id)
        if key_anx in self._openings:
            return self._openings[key_anx]
        # Generic anxiety opening
        if (anx, "medium") in self._generic_openings:
            return self._generic_openings[(anx, "medium")]
        # Generic interest
        if ("medium", intr) in self._generic_openings:
            return self._generic_openings[("medium", intr)]
        return HARDCODED_FALLBACK

    async def personalise(self, student_id: str, feedback_body: str, kc_id: str) -> str:
        """Retrieve profile, select opening, combine with body, log event."""
        profile = await self._scorer.get_profile(student_id)
        if profile and profile.is_complete:
            anxiety_level = profile.anxiety_level
            interest_level = profile.interest_level
        else:
            # Fallback for missing/incomplete profile
            anxiety_level = AffectiveLevel.MEDIUM
            interest_level = AffectiveLevel.MEDIUM

        opening = self.select_opening(anxiety_level, interest_level, kc_id)
        full_message = f"{opening}\n\n{feedback_body}"

        # Log personalisation event
        await self._log_event(student_id, kc_id, anxiety_level, interest_level, opening, feedback_body, full_message)
        return full_message

    async def _log_event(self, student_id: str, kc_id: str, anxiety_level: AffectiveLevel,
                         interest_level: AffectiveLevel, opening: str, body: str, full: str) -> None:
        try:
            async with self._db.acquire() as conn:
                await conn.execute(
                    """INSERT INTO feedback_personalisation (student_id, kc_id, anxiety_level, interest_level, opening_used, feedback_body, full_message)
                       VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                    student_id, kc_id, anxiety_level.value, interest_level.value, opening, body, full,
                )
        except Exception as e:
            logger.error(f"Failed to log personalisation: {e}")

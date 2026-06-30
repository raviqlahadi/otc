import json
from typing import Optional

from models import AffectiveLevel, AffectiveProfile

AMAS_ITEMS = [f"AMAS_0{i}" for i in range(1, 10)]
INTEREST_ITEMS = ["INT_01", "INT_02", "INT_03"]


def compute_anxiety_level(total: int) -> AffectiveLevel:
    """Classify AMAS total (9-45) into anxiety level."""
    if total <= 20:
        return AffectiveLevel.LOW
    elif total <= 32:
        return AffectiveLevel.MEDIUM
    return AffectiveLevel.HIGH


def compute_interest_level(total: int) -> AffectiveLevel:
    """Classify interest total (3-15) into interest level."""
    if total <= 7:
        return AffectiveLevel.LOW
    elif total <= 11:
        return AffectiveLevel.MEDIUM
    return AffectiveLevel.HIGH


def compute_totals(responses: dict[str, str]) -> tuple[int, int]:
    """Sum AMAS and interest scores from response dict."""
    amas_total = sum(int(responses.get(item, "3")) for item in AMAS_ITEMS if item in responses)
    interest_total = sum(int(responses.get(item, "3")) for item in INTEREST_ITEMS if item in responses)
    return amas_total, interest_total


class AffectiveScorer:
    def __init__(self, db_pool):
        self._db = db_pool

    async def score_and_persist(self, student_id: str, responses: dict[str, str]) -> AffectiveProfile:
        """Sum responses, classify levels, upsert to affective_survey table."""
        amas_total, interest_total = compute_totals(responses)
        anxiety_level = compute_anxiety_level(amas_total)
        interest_level = compute_interest_level(interest_total)

        profile = AffectiveProfile(
            student_id=student_id,
            anxiety_total=amas_total,
            anxiety_level=anxiety_level,
            interest_total=interest_total,
            interest_level=interest_level,
            is_complete=True,
        )

        async with self._db.acquire() as conn:
            await conn.execute(
                """INSERT INTO affective_survey (student_id, amas_responses, interest_responses, amas_total, interest_total, anxiety_level, interest_level, is_complete, completed_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, TRUE, NOW())
                   ON CONFLICT (student_id) DO UPDATE SET
                     amas_responses=$2, interest_responses=$3, amas_total=$4, interest_total=$5,
                     anxiety_level=$6, interest_level=$7, is_complete=TRUE, completed_at=NOW()""",
                student_id,
                json.dumps({k: v for k, v in responses.items() if k.startswith("AMAS")}),
                json.dumps({k: v for k, v in responses.items() if k.startswith("INT")}),
                amas_total, interest_total, anxiety_level.value, interest_level.value,
            )
        return profile

    async def get_profile(self, student_id: str) -> Optional[AffectiveProfile]:
        """Retrieve persisted AffectiveProfile. Returns None if not found."""
        async with self._db.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT amas_total, interest_total, anxiety_level, interest_level, is_complete FROM affective_survey WHERE student_id = $1",
                student_id,
            )
            if not row:
                return None
            return AffectiveProfile(
                student_id=student_id,
                anxiety_total=row["amas_total"] or 0,
                anxiety_level=AffectiveLevel(row["anxiety_level"]) if row["anxiety_level"] else AffectiveLevel.MEDIUM,
                interest_total=row["interest_total"] or 0,
                interest_level=AffectiveLevel(row["interest_level"]) if row["interest_level"] else AffectiveLevel.MEDIUM,
                is_complete=row["is_complete"],
            )

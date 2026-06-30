from typing import Optional

from models.assessment import Question


class QuestionRepository:
    def __init__(self, db_pool):
        self._db = db_pool

    async def get_by_id(self, question_id: str) -> Optional[Question]:
        async with self._db.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM questions WHERE id = $1", question_id)
            if not row:
                return None
            return self._row_to_question(row)

    async def get_by_kc(self, kc_id: str, exclude_ids: list[str] = None) -> Optional[Question]:
        """Get first available question for a KC, optionally excluding already-seen."""
        async with self._db.acquire() as conn:
            if exclude_ids:
                row = await conn.fetchrow(
                    "SELECT * FROM questions WHERE kc_id = $1 AND id != ALL($2::text[]) AND is_verification = false LIMIT 1",
                    kc_id, exclude_ids,
                )
            else:
                row = await conn.fetchrow(
                    "SELECT * FROM questions WHERE kc_id = $1 AND is_verification = false LIMIT 1",
                    kc_id,
                )
            return self._row_to_question(row) if row else None

    async def get_verification(self, kc_id: str, misconception_id: str, exclude_id: str = None) -> Optional[Question]:
        """Get a verification question for a specific misconception."""
        async with self._db.acquire() as conn:
            if exclude_id:
                row = await conn.fetchrow(
                    """SELECT * FROM questions WHERE kc_id = $1 AND is_verification = true
                       AND target_misconception_id = $2 AND id != $3 LIMIT 1""",
                    kc_id, misconception_id, exclude_id,
                )
            else:
                row = await conn.fetchrow(
                    "SELECT * FROM questions WHERE kc_id = $1 AND is_verification = true AND target_misconception_id = $2 LIMIT 1",
                    kc_id, misconception_id,
                )
            return self._row_to_question(row) if row else None

    @staticmethod
    def _row_to_question(row) -> Question:
        distractor_map = {}
        if row.get("distractor_map"):
            import json
            distractor_map = json.loads(row["distractor_map"]) if isinstance(row["distractor_map"], str) else row["distractor_map"]
        return Question(
            id=row["id"], kc_id=row["kc_id"], question_text=row["question_text"],
            correct_option=row["correct_option"],
            option_a=row["option_a"], option_b=row["option_b"],
            option_c=row["option_c"], option_d=row["option_d"],
            distractor_map=distractor_map,
            is_verification=row.get("is_verification", False),
            target_misconception_id=row.get("target_misconception_id"),
        )

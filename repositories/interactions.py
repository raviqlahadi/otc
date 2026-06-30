from typing import Optional


class InteractionRepository:
    def __init__(self, db_pool):
        self._db = db_pool

    async def log(self, student_id: str, question_id: str, session_id: str,
                  attempt_number: int, selected_option: str, is_correct: bool,
                  misconception_id: Optional[str]) -> None:
        async with self._db.acquire() as conn:
            await conn.execute(
                """INSERT INTO interactions (student_id, question_id, session_id, attempt_number, selected_option, is_correct, misconception_id)
                   VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                student_id, question_id, session_id, attempt_number, selected_option, is_correct, misconception_id,
            )

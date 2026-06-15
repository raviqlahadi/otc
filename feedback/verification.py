import logging
from typing import Optional

from models import Question

logger = logging.getLogger(__name__)


class VerificationSelector:
    def __init__(self, db_pool):
        self._db = db_pool

    async def select_verification_question(self, kc_id: str, misconception_id: str, original_question_id: str) -> Optional[Question]:
        """Select a verification question: different from original, same KC, targets same misconception."""
        async with self._db.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT id, kc_id, question_text, correct_option, option_a, option_b, option_c, option_d, target_misconception_id
                   FROM questions
                   WHERE kc_id = $1 AND is_verification = TRUE AND target_misconception_id = $2 AND id != $3
                   LIMIT 1""",
                kc_id, misconception_id, original_question_id,
            )
            if not row:
                logger.warning(f"No verification question for kc={kc_id} misconception={misconception_id}")
                return None
            # Load distractor mappings
            mappings = await conn.fetch(
                "SELECT option_letter, misconception_id FROM distractor_mappings WHERE question_id = $1",
                row["id"],
            )
            distractor_map = {r["option_letter"]: r["misconception_id"] for r in mappings}
            return Question(
                id=row["id"], kc_id=row["kc_id"], question_text=row["question_text"],
                correct_option=row["correct_option"],
                option_a=row["option_a"], option_b=row["option_b"],
                option_c=row["option_c"], option_d=row["option_d"],
                distractor_map=distractor_map,
                is_verification=True, target_misconception_id=row["target_misconception_id"],
            )

    async def process_verification_answer(self, student_id: str, kc_id: str, question: Question, selected_option: str, misconception_id_targeted: str) -> str:
        """Process verification answer. Returns 'mastered' or 'needs_review'."""
        is_correct = selected_option.upper() == question.correct_option

        async with self._db.acquire() as conn:
            await conn.execute(
                """INSERT INTO verification_results (student_id, kc_id, verification_question_id, selected_option, is_correct, misconception_id_targeted)
                   VALUES ($1, $2, $3, $4, $5, $6)""",
                student_id, kc_id, question.id, selected_option, is_correct, misconception_id_targeted,
            )
            status = "mastered" if is_correct else "needs_review"
            await conn.execute(
                "UPDATE student_mastery SET status = $1 WHERE student_id = $2 AND kc_id = $3",
                status, student_id, kc_id,
            )
        return status

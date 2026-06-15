from models import FeedbackContent


class FeedbackGenerator:
    def __init__(self, db_pool):
        self._db = db_pool

    async def get_feedback(self, question_id: str, misconception_id: str) -> FeedbackContent:
        """Retrieve misconception-specific feedback. Falls back to generic if not available."""
        async with self._db.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT name, description, why_incorrect, correct_method FROM misconceptions WHERE id = $1",
                misconception_id,
            )
            if row:
                return FeedbackContent(
                    misconception_name=row["name"],
                    misconception_description=row["description"],
                    why_incorrect=row["why_incorrect"],
                    correct_method=row["correct_method"],
                    is_generic=False,
                )
            # Generic fallback
            q_row = await conn.fetchrow("SELECT question_text, correct_option FROM questions WHERE id = $1", question_id)
            correct_method = f"Jawaban yang benar adalah {q_row['correct_option']}." if q_row else "Silakan periksa kembali."
            return FeedbackContent(
                misconception_name="", misconception_description="",
                why_incorrect="", correct_method=correct_method, is_generic=True,
            )

    @staticmethod
    def format_feedback_message(feedback: FeedbackContent) -> str:
        """Format feedback into plain-text WhatsApp message."""
        if feedback.is_generic:
            return f"📝 Feedback:\n\nCara yang benar:\n{feedback.correct_method}"
        return (
            f"📝 Feedback:\n\n"
            f"Miskonsepsi yang terdeteksi: {feedback.misconception_name}\n"
            f"{feedback.misconception_description}\n\n"
            f"Mengapa keliru:\n{feedback.why_incorrect}\n\n"
            f"Cara yang benar:\n{feedback.correct_method}"
        )

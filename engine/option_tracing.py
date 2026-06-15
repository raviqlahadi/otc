import time
from typing import Optional

from models import AnswerResult, BKTParams, Question, StudentMastery


class OptionTracingEngine:
    def __init__(self, db_pool, bkt_params: dict[str, BKTParams]):
        self._db = db_pool
        self._params = bkt_params

    async def initialize_student(self, student_id: str) -> None:
        """Initialize mastery records for a new student using pre-calibrated P(L₀) values."""
        async with self._db.acquire() as conn:
            for kc_id, params in self._params.items():
                await conn.execute(
                    """INSERT INTO student_mastery (student_id, kc_id, p_mastery, p_transition)
                       VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING""",
                    student_id, kc_id, params.p_l0, params.p_transit,
                )

    def compute_mastery_update(self, mastery: StudentMastery, correct: bool, params: BKTParams) -> StudentMastery:
        """Pure BKT posterior update. Returns updated mastery (no side effects)."""
        if correct:
            p_obs_given_mastery = 1 - params.p_slip
            p_obs_given_not = params.p_guess
        else:
            p_obs_given_mastery = params.p_slip
            p_obs_given_not = 1 - params.p_guess

        p_obs = p_obs_given_mastery * mastery.p_mastery + p_obs_given_not * (1 - mastery.p_mastery)
        if p_obs == 0:
            posterior = mastery.p_mastery
        else:
            posterior = (p_obs_given_mastery * mastery.p_mastery) / p_obs

        # Transition update
        mastery.p_mastery = posterior + mastery.p_transition * (1 - posterior)
        mastery.p_mastery = max(0.0, min(1.0, mastery.p_mastery))
        mastery.last_updated = time.time()
        return mastery

    async def process_answer(self, student_id: str, question: Question, selected_option: str, attempt_number: int, session_id: str) -> AnswerResult:
        """Process answer: check correctness, identify misconception, log, update mastery."""
        is_correct = selected_option.upper() == question.correct_option
        misconception_id = None if is_correct else question.distractor_map.get(selected_option.upper())

        await self._log_interaction(student_id, question.id, session_id, attempt_number, selected_option, is_correct, misconception_id)

        mastery = await self._load_mastery(student_id, question.kc_id)
        params = self._params[question.kc_id]
        mastery = self.compute_mastery_update(mastery, is_correct, params)

        if misconception_id:
            await self._update_misconception_prob(student_id, question.kc_id, misconception_id)

        await self._save_mastery(mastery)
        return AnswerResult(is_correct=is_correct, misconception_id=misconception_id, attempt_number=attempt_number, updated_mastery=mastery)

    async def _log_interaction(self, student_id, question_id, session_id, attempt_number, selected_option, is_correct, misconception_id):
        async with self._db.acquire() as conn:
            await conn.execute(
                """INSERT INTO interactions (student_id, question_id, session_id, attempt_number, selected_option, is_correct, misconception_id)
                   VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                student_id, question_id, session_id, attempt_number, selected_option, is_correct, misconception_id,
            )

    async def _load_mastery(self, student_id: str, kc_id: str) -> StudentMastery:
        async with self._db.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT p_mastery, p_transition FROM student_mastery WHERE student_id = $1 AND kc_id = $2",
                student_id, kc_id,
            )
            if row:
                return StudentMastery(student_id=student_id, kc_id=kc_id, p_mastery=row["p_mastery"], p_transition=row["p_transition"])
            params = self._params.get(kc_id, BKTParams(0.3, 0.25, 0.1, 0.1))
            return StudentMastery(student_id=student_id, kc_id=kc_id, p_mastery=params.p_l0, p_transition=params.p_transit)

    async def _save_mastery(self, mastery: StudentMastery):
        async with self._db.acquire() as conn:
            await conn.execute(
                """INSERT INTO student_mastery (student_id, kc_id, p_mastery, p_transition, last_updated)
                   VALUES ($1, $2, $3, $4, NOW())
                   ON CONFLICT (student_id, kc_id) DO UPDATE SET p_mastery = $3, p_transition = $4, last_updated = NOW()""",
                mastery.student_id, mastery.kc_id, mastery.p_mastery, mastery.p_transition,
            )

    async def _update_misconception_prob(self, student_id: str, kc_id: str, misconception_id: str):
        async with self._db.acquire() as conn:
            await conn.execute(
                """INSERT INTO student_misconception_probs (student_id, kc_id, misconception_id, probability, occurrence_count)
                   VALUES ($1, $2, $3, 0.0, 1)
                   ON CONFLICT (student_id, kc_id, misconception_id) DO UPDATE SET
                     occurrence_count = student_misconception_probs.occurrence_count + 1""",
                student_id, kc_id, misconception_id,
            )
            # Recompute probabilities
            rows = await conn.fetch(
                "SELECT misconception_id, occurrence_count FROM student_misconception_probs WHERE student_id = $1 AND kc_id = $2",
                student_id, kc_id,
            )
            total = sum(r["occurrence_count"] for r in rows)
            for r in rows:
                prob = r["occurrence_count"] / total if total > 0 else 0.0
                await conn.execute(
                    "UPDATE student_misconception_probs SET probability = $1 WHERE student_id = $2 AND kc_id = $3 AND misconception_id = $4",
                    prob, student_id, kc_id, r["misconception_id"],
                )

    def classify_misconception_pattern(self, selected_options: list[dict]) -> tuple[str, str]:
        """Classify misconception pattern from attempt history.
        Returns (dominant_misconception_id, 'consistent' | 'varied')."""
        counts: dict[str, int] = {}
        last_misconception: Optional[str] = None
        for entry in selected_options:
            m_id = entry.get("misconception_id")
            if m_id:
                counts[m_id] = counts.get(m_id, 0) + 1
                last_misconception = m_id

        if not counts:
            return ("unknown", "varied")

        max_count = max(counts.values())
        pattern = "consistent" if max_count >= 2 else "varied"
        dominant_candidates = [m for m, c in counts.items() if c == max_count]

        if len(dominant_candidates) > 1:
            dominant = last_misconception or dominant_candidates[0]
        else:
            dominant = dominant_candidates[0]

        return (dominant, pattern)

    async def get_next_kc(self, student_id: str, current_kc_id: str) -> Optional[str]:
        """Get next unmastered KC respecting prerequisite order."""
        async with self._db.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, prerequisite_kc_id FROM knowledge_components ORDER BY display_order"
            )
            mastered = await conn.fetch(
                "SELECT kc_id FROM student_mastery WHERE student_id = $1 AND (status = 'mastered' OR p_mastery >= 0.8)",
                student_id,
            )
            mastered_ids = {r["kc_id"] for r in mastered}
            mastered_ids.add(current_kc_id)

            for row in rows:
                kc_id = row["id"]
                if kc_id in mastered_ids:
                    continue
                prereq = row["prerequisite_kc_id"]
                if prereq is None or prereq in mastered_ids:
                    return kc_id
        return None

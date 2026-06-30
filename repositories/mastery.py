from models.assessment import BKTParams, StudentMastery


class MasteryRepository:
    def __init__(self, db_pool):
        self._db = db_pool

    async def load(self, student_id: str, kc_id: str, default_params: BKTParams = None) -> StudentMastery:
        async with self._db.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT p_mastery, p_transition FROM student_mastery WHERE student_id = $1 AND kc_id = $2",
                student_id, kc_id,
            )
            if row:
                return StudentMastery(student_id=student_id, kc_id=kc_id, p_mastery=row["p_mastery"], p_transition=row["p_transition"])
            p = default_params or BKTParams(0.3, 0.25, 0.1, 0.1)
            return StudentMastery(student_id=student_id, kc_id=kc_id, p_mastery=p.p_l0, p_transition=p.p_transit)

    async def save(self, mastery: StudentMastery) -> None:
        async with self._db.acquire() as conn:
            await conn.execute(
                """INSERT INTO student_mastery (student_id, kc_id, p_mastery, p_transition, last_updated)
                   VALUES ($1, $2, $3, $4, NOW())
                   ON CONFLICT (student_id, kc_id) DO UPDATE SET p_mastery = $3, p_transition = $4, last_updated = NOW()""",
                mastery.student_id, mastery.kc_id, mastery.p_mastery, mastery.p_transition,
            )

    async def initialize_student(self, student_id: str, params: dict[str, BKTParams]) -> None:
        async with self._db.acquire() as conn:
            for kc_id, p in params.items():
                await conn.execute(
                    """INSERT INTO student_mastery (student_id, kc_id, p_mastery, p_transition)
                       VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING""",
                    student_id, kc_id, p.p_l0, p.p_transit,
                )

    async def update_misconception_prob(self, student_id: str, kc_id: str, misconception_id: str) -> None:
        async with self._db.acquire() as conn:
            await conn.execute(
                """INSERT INTO student_misconception_probs (student_id, kc_id, misconception_id, probability, occurrence_count)
                   VALUES ($1, $2, $3, 0.0, 1)
                   ON CONFLICT (student_id, kc_id, misconception_id) DO UPDATE SET
                     occurrence_count = student_misconception_probs.occurrence_count + 1""",
                student_id, kc_id, misconception_id,
            )
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

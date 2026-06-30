from typing import Optional


class ProgressRepository:
    def __init__(self, db_pool):
        self._db = db_pool

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

    async def save(self, student_id: str, current_kc_id: str, session_id: str) -> None:
        async with self._db.acquire() as conn:
            await conn.execute(
                """INSERT INTO student_progress (student_id, current_kc_id, completed_kc_ids, last_session_id, updated_at)
                   VALUES ($1, $2, $3, $4, NOW())
                   ON CONFLICT (student_id) DO UPDATE SET
                     current_kc_id = $2, completed_kc_ids = $3, last_session_id = $4, updated_at = NOW()""",
                student_id, current_kc_id, [], session_id,
            )

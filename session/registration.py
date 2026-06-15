import hashlib
import uuid
from typing import Optional


class StudentRegistration:
    def __init__(self, db_pool, engine):
        self._db = db_pool
        self._engine = engine

    @staticmethod
    def hash_phone(phone: str) -> str:
        """SHA-256 hash of the phone number."""
        return hashlib.sha256(phone.encode()).hexdigest()

    async def get_or_register(self, phone: str) -> str:
        """Return student_id. Register if new."""
        phone_hash = self.hash_phone(phone)
        async with self._db.acquire() as conn:
            row = await conn.fetchrow("SELECT id FROM students WHERE phone_hash = $1", phone_hash)
            if row:
                await conn.execute("UPDATE students SET last_active_at = NOW() WHERE id = $1", row["id"])
                return row["id"]
            # New student
            student_id = str(uuid.uuid4())[:20]
            await conn.execute(
                "INSERT INTO students (id, phone_hash) VALUES ($1, $2)",
                student_id, phone_hash,
            )
            await self._engine.initialize_student(student_id)
            return student_id

    async def get_progress(self, student_id: str) -> Optional[dict]:
        """Load persisted progress for session resumption."""
        async with self._db.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT current_kc_id, completed_kc_ids, last_session_id FROM student_progress WHERE student_id = $1",
                student_id,
            )
            if row:
                return {
                    "current_kc_id": row["current_kc_id"],
                    "completed_kc_ids": row["completed_kc_ids"] or [],
                    "last_session_id": row["last_session_id"],
                }
        return None

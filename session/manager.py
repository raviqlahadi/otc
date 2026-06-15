import json
from typing import Optional

from models import FlowPhase, SessionState


class SessionManager:
    SESSION_TTL = 86400  # 24 hours

    def __init__(self, redis_client, db_pool):
        self._redis = redis_client
        self._db = db_pool

    async def get_session(self, student_id: str) -> Optional[SessionState]:
        """Load session from Redis, fall back to PostgreSQL for resumption."""
        key = f"session:{student_id}"
        data = await self._redis.hgetall(key)
        if data:
            return self._deserialize(data)
        return await self._load_from_db(student_id)

    async def save_session(self, state: SessionState) -> None:
        """Persist session state to Redis with TTL."""
        key = f"session:{state.student_id}"
        await self._redis.hset(key, mapping=self._serialize(state))
        await self._redis.expire(key, self.SESSION_TTL)

    async def persist_progress(self, state: SessionState) -> None:
        """Save progress to PostgreSQL for cross-session continuity."""
        async with self._db.acquire() as conn:
            await conn.execute(
                """INSERT INTO student_progress (student_id, current_kc_id, completed_kc_ids, last_session_id, updated_at)
                   VALUES ($1, $2, $3, $4, NOW())
                   ON CONFLICT (student_id) DO UPDATE SET
                     current_kc_id = $2, completed_kc_ids = $3, last_session_id = $4, updated_at = NOW()""",
                state.student_id, state.current_kc_id, [], state.session_id,
            )

    async def increment_attempt(self, state: SessionState) -> SessionState:
        """Increment attempt count, transition phase if max reached."""
        state.attempt_count += 1
        if state.attempt_count >= 3:
            state.flow_phase = FlowPhase.FEEDBACK
        else:
            state.flow_phase = FlowPhase.RETRY
        await self.save_session(state)
        return state

    def _serialize(self, state: SessionState) -> dict[str, str]:
        return {
            "student_id": state.student_id,
            "current_kc_id": state.current_kc_id,
            "current_question_id": state.current_question_id or "",
            "attempt_count": str(state.attempt_count),
            "flow_phase": state.flow_phase.value,
            "selected_options": json.dumps(state.selected_options),
            "session_id": state.session_id,
        }

    def _deserialize(self, data: dict) -> SessionState:
        # Handle bytes from Redis
        d = {k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v for k, v in data.items()}
        return SessionState(
            student_id=d["student_id"],
            current_kc_id=d["current_kc_id"],
            current_question_id=d["current_question_id"] or None,
            attempt_count=int(d["attempt_count"]),
            flow_phase=FlowPhase(d["flow_phase"]),
            selected_options=json.loads(d["selected_options"]),
            session_id=d["session_id"],
        )

    async def _load_from_db(self, student_id: str) -> Optional[SessionState]:
        """Load last progress from PostgreSQL for session resumption."""
        async with self._db.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT current_kc_id, last_session_id FROM student_progress WHERE student_id = $1",
                student_id,
            )
            if row:
                return SessionState(
                    student_id=student_id,
                    current_kc_id=row["current_kc_id"],
                    current_question_id=None,
                    attempt_count=0,
                    flow_phase=FlowPhase.QUESTION,
                    selected_options=[],
                    session_id=row["last_session_id"] or "",
                )
        return None

import csv
import hashlib
from io import StringIO


class AnalyticsModule:
    def __init__(self, db_pool):
        self._db = db_pool

    @staticmethod
    def _anonymize(student_id: str) -> str:
        return hashlib.sha256(student_id.encode()).hexdigest()[:16]

    async def export_learning_trajectories(self) -> str:
        """Per-student interactions ordered by timestamp, CSV format."""
        async with self._db.acquire() as conn:
            rows = await conn.fetch(
                "SELECT student_id, question_id, attempt_number, selected_option, is_correct, misconception_id, timestamp "
                "FROM interactions ORDER BY student_id, timestamp"
            )
        buf = StringIO()
        w = csv.writer(buf)
        w.writerow(["student_id", "question_id", "attempt_number", "selected_option", "is_correct", "misconception_id", "timestamp"])
        for r in rows:
            w.writerow([self._anonymize(r["student_id"]), r["question_id"], r["attempt_number"],
                        r["selected_option"], r["is_correct"], r["misconception_id"] or "", str(r["timestamp"])])
        return buf.getvalue()

    async def export_misconception_frequencies(self) -> str:
        """Population-level misconception frequency per KC, CSV format."""
        async with self._db.acquire() as conn:
            rows = await conn.fetch(
                "SELECT q.kc_id, i.misconception_id, COUNT(*) as count "
                "FROM interactions i JOIN questions q ON i.question_id = q.id "
                "WHERE i.misconception_id IS NOT NULL "
                "GROUP BY q.kc_id, i.misconception_id ORDER BY q.kc_id, count DESC"
            )
        buf = StringIO()
        w = csv.writer(buf)
        w.writerow(["kc_id", "misconception_id", "count"])
        for r in rows:
            w.writerow([r["kc_id"], r["misconception_id"], r["count"]])
        return buf.getvalue()

    async def export_diagnostic_outputs(self) -> str:
        """P(mastery), P(transition), P(misconception) for all students, CSV format."""
        async with self._db.acquire() as conn:
            mastery_rows = await conn.fetch(
                "SELECT student_id, kc_id, p_mastery, p_transition, status FROM student_mastery ORDER BY student_id, kc_id"
            )
            misc_rows = await conn.fetch(
                "SELECT student_id, kc_id, misconception_id, probability FROM student_misconception_probs ORDER BY student_id, kc_id"
            )
        # Build misconception prob lookup
        misc_lookup: dict[tuple, list] = {}
        for r in misc_rows:
            key = (r["student_id"], r["kc_id"])
            misc_lookup.setdefault(key, []).append((r["misconception_id"], r["probability"]))

        buf = StringIO()
        w = csv.writer(buf)
        w.writerow(["student_id", "kc_id", "p_mastery", "p_transition", "status", "misconception_probs"])
        for r in mastery_rows:
            probs = misc_lookup.get((r["student_id"], r["kc_id"]), [])
            probs_str = ";".join(f"{m}:{p:.4f}" for m, p in probs)
            w.writerow([self._anonymize(r["student_id"]), r["kc_id"], f"{r['p_mastery']:.4f}",
                        f"{r['p_transition']:.4f}", r["status"], probs_str])
        return buf.getvalue()

    async def export_affective_profiles(self) -> str:
        """Export affective survey data with anonymised student IDs, CSV format."""
        async with self._db.acquire() as conn:
            rows = await conn.fetch(
                "SELECT student_id, amas_total, interest_total, anxiety_level, interest_level, is_complete, completed_at "
                "FROM affective_survey ORDER BY student_id"
            )
        buf = StringIO()
        w = csv.writer(buf)
        w.writerow(["student_id", "amas_total", "interest_total", "anxiety_level", "interest_level", "is_complete", "completed_at"])
        for r in rows:
            w.writerow([self._anonymize(r["student_id"]), r["amas_total"], r["interest_total"],
                        r["anxiety_level"], r["interest_level"], r["is_complete"], str(r["completed_at"] or "")])
        return buf.getvalue()

    async def export_feedback_personalisation_log(self) -> str:
        """Export feedback personalisation audit log, CSV format."""
        async with self._db.acquire() as conn:
            rows = await conn.fetch(
                "SELECT student_id, kc_id, anxiety_level, interest_level, opening_used, created_at "
                "FROM feedback_personalisation ORDER BY student_id, created_at"
            )
        buf = StringIO()
        w = csv.writer(buf)
        w.writerow(["student_id", "kc_id", "anxiety_level", "interest_level", "opening_used", "timestamp"])
        for r in rows:
            w.writerow([self._anonymize(r["student_id"]), r["kc_id"], r["anxiety_level"],
                        r["interest_level"], r["opening_used"], str(r["created_at"])])
        return buf.getvalue()

    async def export_full_research_dump(self) -> dict[str, str]:
        """Export all research data as a dict of filename -> CSV content."""
        return {
            "learning_trajectories.csv": await self.export_learning_trajectories(),
            "misconception_frequencies.csv": await self.export_misconception_frequencies(),
            "diagnostic_outputs.csv": await self.export_diagnostic_outputs(),
            "affective_profiles.csv": await self.export_affective_profiles(),
            "feedback_personalisation_log.csv": await self.export_feedback_personalisation_log(),
        }

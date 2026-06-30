import logging

from engine.option_tracing import OptionTracingEngine
from feedback.generator import FeedbackGenerator
from feedback.personaliser import FeedbackPersonaliser
from feedback.verification import VerificationSelector
from models.assessment import Question
from models.session import FlowPhase, SessionState
from repositories.questions import QuestionRepository
from server.formatting import format_question
from session.manager import SessionManager
from survey.conductor import SurveyConductor
from survey.scorer import AffectiveScorer
from validation.input_validator import validate_answer

logger = logging.getLogger(__name__)


class FlowController:
    """Orchestrates the conversation state machine. All dependencies injected via __init__."""

    def __init__(
        self,
        session_mgr: SessionManager,
        engine: OptionTracingEngine,
        feedback_gen: FeedbackGenerator,
        verification: VerificationSelector,
        question_repo: QuestionRepository,
        survey_conductor: SurveyConductor = None,
        scorer: AffectiveScorer = None,
        personaliser: FeedbackPersonaliser = None,
    ):
        self.session_mgr = session_mgr
        self.engine = engine
        self.feedback_gen = feedback_gen
        self.verification = verification
        self.question_repo = question_repo
        self.survey_conductor = survey_conductor
        self.scorer = scorer
        self.personaliser = personaliser

    async def handle(self, text: str, student_id: str) -> str:
        """Main entry point — process a student message and return response."""
        session = await self.session_mgr.get_session(student_id)

        if session is None:
            return await self._start_new_session(student_id)

        if session.flow_phase == FlowPhase.DEMOGRAPHIC_SURVEY:
            return await self._handle_survey(text, student_id, session, "demographic")

        if session.flow_phase == FlowPhase.AFFECTIVE_SURVEY:
            return await self._handle_survey(text, student_id, session, "affective")

        if session.flow_phase == FlowPhase.COMPLETED:
            return "🎉 Selamat! Kamu sudah menyelesaikan semua materi assessment."

        # Assessment phases
        valid, option = validate_answer(text)
        if not valid:
            return "Silakan balas dengan A, B, C, atau D."

        question = await self._load_current_question(session)
        if not question:
            return "Tidak ada soal yang tersedia."

        if session.flow_phase == FlowPhase.VERIFICATION:
            return await self._handle_verification(option, session, question)

        # QUESTION or RETRY — process answer
        is_correct = option == question.correct_option
        if is_correct:
            return await self._handle_correct(session)

        return await self._handle_wrong(option, session, question)

    # --- Private handlers ---

    async def _start_new_session(self, student_id: str) -> str:
        if self.survey_conductor:
            session = await self.session_mgr.transition_to_survey(student_id)
            prompt = await self.survey_conductor.start_survey(student_id, "demographic")
            return f"📋 Sebelum memulai, kami ingin mengenal Anda lebih dekat.\n\n{prompt}"

        first_kc = await self.engine.get_next_kc(student_id, "")
        if not first_kc:
            return "Tidak ada materi yang tersedia saat ini."

        session = SessionState(
            student_id=student_id, current_kc_id=first_kc,
            current_question_id=None, attempt_count=0,
            flow_phase=FlowPhase.QUESTION, selected_options=[],
        )
        await self.session_mgr.save_session(session)
        return await self._serve_question(session)

    async def _handle_survey(self, text: str, student_id: str, session: SessionState, section: str) -> str:
        if not self.survey_conductor:
            first_kc = await self.engine.get_next_kc(student_id, "")
            if first_kc:
                await self.session_mgr.transition_to_assessment(session, first_kc)
            return "Survei tidak tersedia. Melanjutkan ke assessment."

        next_prompt = await self.survey_conductor.process_response(student_id, text)
        if next_prompt is not None:
            return next_prompt

        # Section complete
        if section == "demographic":
            await self.session_mgr.transition_to_affective_survey(session)
            prompt = await self.survey_conductor.start_survey(student_id, "affective")
            return f"✅ Terima kasih!\n\nSekarang beberapa pertanyaan tentang perasaan Anda terhadap matematika.\n\n{prompt}"

        # Affective complete — score and start assessment
        responses = await self.survey_conductor.get_responses(student_id)
        if self.scorer:
            await self.scorer.score_and_persist(student_id, responses)

        first_kc = await self.engine.get_next_kc(student_id, "")
        if not first_kc:
            session.flow_phase = FlowPhase.COMPLETED
            await self.session_mgr.save_session(session)
            return "Tidak ada materi yang tersedia saat ini."

        await self.session_mgr.transition_to_assessment(session, first_kc)
        return "✅ Terima kasih sudah mengisi survei!\n\nSekarang kita mulai assessment matematika. Jawab soal berikut dengan A, B, C, atau D."

    async def _handle_correct(self, session: SessionState) -> str:
        next_kc = await self.engine.get_next_kc(session.student_id, session.current_kc_id)
        if next_kc is None:
            session.flow_phase = FlowPhase.COMPLETED
            await self.session_mgr.save_session(session)
            return "✅ Benar! 🎉 Selamat! Kamu sudah menyelesaikan semua materi assessment."

        session.current_kc_id = next_kc
        session.current_question_id = None
        session.attempt_count = 0
        session.flow_phase = FlowPhase.QUESTION
        session.selected_options = []
        await self.session_mgr.save_session(session)

        question = await self._serve_question(session)
        return f"✅ Benar!\n\n{question}" if "Soal" in question or "soal" in question else f"✅ Benar!\n\nSoal berikutnya:\n{question}"

    async def _handle_wrong(self, option: str, session: SessionState, question: Question) -> str:
        session.selected_options.append({
            "attempt": session.attempt_count + 1,
            "option": option,
            "misconception_id": question.distractor_map.get(option, ""),
        })
        session = await self.session_mgr.increment_attempt(session)

        if session.flow_phase == FlowPhase.FEEDBACK:
            return await self._handle_feedback(session, question)

        remaining = 3 - session.attempt_count
        return f"❌ Jawaban salah. Kamu punya {remaining} kesempatan lagi.\n\n{format_question(question)}"

    async def _handle_feedback(self, session: SessionState, question: Question) -> str:
        dominant_id, pattern = self.engine.classify_misconception_pattern(session.selected_options)
        feedback = await self.feedback_gen.get_feedback(question.id, dominant_id)
        feedback_msg = FeedbackGenerator.format_feedback_message(feedback)

        if self.personaliser:
            feedback_msg = await self.personaliser.personalise(session.student_id, feedback_msg, session.current_kc_id)

        verif_q = await self.verification.select_verification_question(
            session.current_kc_id, dominant_id, question.id
        )
        if verif_q:
            session.flow_phase = FlowPhase.VERIFICATION
            session.current_question_id = verif_q.id
            session.attempt_count = 0
            await self.session_mgr.save_session(session)
            return f"❌ Jawaban salah.\n\n{feedback_msg}\n\nSoal verifikasi:\n{format_question(verif_q)}"

        # No verification — advance
        return await self._advance_after_feedback(session, feedback_msg)

    async def _handle_verification(self, option: str, session: SessionState, question: Question) -> str:
        is_correct = option == question.correct_option
        dominant_id = ""
        if session.selected_options:
            dominant_id = session.selected_options[-1].get("misconception_id", "")

        await self.verification.process_verification_answer(
            session.student_id, session.current_kc_id, question, option, dominant_id
        )

        next_kc = await self.engine.get_next_kc(session.student_id, session.current_kc_id)
        if next_kc is None:
            session.flow_phase = FlowPhase.COMPLETED
            await self.session_mgr.save_session(session)
            prefix = "✅ Selamat sudah mahir!" if is_correct else "❌ Jawaban salah. Materi ini perlu dipelajari kembali."
            return f"{prefix} 🎉 Assessment selesai."

        session.current_kc_id = next_kc
        session.current_question_id = None
        session.attempt_count = 0
        session.flow_phase = FlowPhase.QUESTION
        session.selected_options = []
        await self.session_mgr.save_session(session)

        prefix = "✅ Selamat sudah mahir!" if is_correct else "❌ Jawaban salah. Materi ini perlu dipelajari kembali."
        q_text = await self._serve_question(session)
        return f"{prefix}\n\n{q_text}"

    async def _advance_after_feedback(self, session: SessionState, feedback_msg: str) -> str:
        next_kc = await self.engine.get_next_kc(session.student_id, session.current_kc_id)
        if next_kc is None:
            session.flow_phase = FlowPhase.COMPLETED
            await self.session_mgr.save_session(session)
            return f"❌ Jawaban salah.\n\n{feedback_msg}\n\n🎉 Assessment selesai."

        session.current_kc_id = next_kc
        session.current_question_id = None
        session.attempt_count = 0
        session.flow_phase = FlowPhase.QUESTION
        session.selected_options = []
        await self.session_mgr.save_session(session)

        q_text = await self._serve_question(session)
        return f"❌ Jawaban salah.\n\n{feedback_msg}\n\nSoal berikutnya:\n{q_text}"

    # --- Helpers ---

    async def _load_current_question(self, session: SessionState) -> Question | None:
        if session.current_question_id:
            return await self.question_repo.get_by_id(session.current_question_id)
        q = await self.question_repo.get_by_kc(session.current_kc_id)
        if q:
            session.current_question_id = q.id
            await self.session_mgr.save_session(session)
        return q

    async def _serve_question(self, session: SessionState) -> str:
        question = await self.question_repo.get_by_kc(session.current_kc_id)
        if question:
            session.current_question_id = question.id
            await self.session_mgr.save_session(session)
            return format_question(question)
        return "Tidak ada soal berikutnya."

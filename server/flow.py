import logging

from engine.option_tracing import OptionTracingEngine
from feedback.generator import FeedbackGenerator
from feedback.verification import VerificationSelector
from models import FlowPhase, Question, SessionState
from server.formatting import format_question
from session.manager import SessionManager
from validation.input_validator import validate_answer

logger = logging.getLogger(__name__)


async def process_message(
    text: str,
    student_id: str,
    session_mgr: SessionManager,
    engine: OptionTracingEngine,
    feedback_gen: FeedbackGenerator,
    verification: VerificationSelector,
    get_question_fn,  # async fn(kc_id) -> Question
) -> str:
    """Orchestrate the conversation state machine. Returns response text."""
    session = await session_mgr.get_session(student_id)

    if session is None:
        # New student — initialize
        first_kc = await engine.get_next_kc(student_id, "")
        if not first_kc:
            return "Tidak ada materi yang tersedia saat ini."
        session = SessionState(
            student_id=student_id, current_kc_id=first_kc,
            current_question_id=None, attempt_count=0,
            flow_phase=FlowPhase.QUESTION, selected_options=[], session_id="",
        )

    if session.flow_phase == FlowPhase.COMPLETED:
        return "🎉 Selamat! Kamu sudah menyelesaikan semua materi assessment."

    # Validate input
    valid, option = validate_answer(text)
    if not valid:
        return "Silakan balas dengan A, B, C, atau D."

    # Load current question
    if session.current_question_id:
        question = await get_question_fn(session.current_question_id)
    else:
        question = await get_question_fn(session.current_kc_id)
        if not question:
            return "Tidak ada soal yang tersedia."
        session.current_question_id = question.id
        await session_mgr.save_session(session)

    # VERIFICATION phase
    if session.flow_phase == FlowPhase.VERIFICATION:
        return await _handle_verification(option, session, session_mgr, engine, verification, get_question_fn, question)

    # QUESTION or RETRY phase — process answer
    is_correct = option == question.correct_option

    if is_correct:
        return await _handle_correct(session, session_mgr, engine, get_question_fn)

    # Wrong answer
    session.selected_options.append({
        "attempt": session.attempt_count + 1,
        "option": option,
        "misconception_id": question.distractor_map.get(option, ""),
    })
    session = await session_mgr.increment_attempt(session)

    if session.flow_phase == FlowPhase.FEEDBACK:
        return await _handle_feedback(session, engine, feedback_gen, verification, session_mgr, question, get_question_fn)

    # Still in RETRY
    remaining = 3 - session.attempt_count
    return f"❌ Jawaban salah. Kamu punya {remaining} kesempatan lagi.\n\n{format_question(question)}"


async def _handle_correct(session, session_mgr, engine, get_question_fn):
    """Handle correct answer — advance to next KC or complete."""
    next_kc = await engine.get_next_kc(session.student_id, session.current_kc_id)
    if next_kc is None:
        session.flow_phase = FlowPhase.COMPLETED
        await session_mgr.save_session(session)
        return "✅ Benar! 🎉 Selamat! Kamu sudah menyelesaikan semua materi assessment."

    # Move to next KC
    session.current_kc_id = next_kc
    session.current_question_id = None
    session.attempt_count = 0
    session.flow_phase = FlowPhase.QUESTION
    session.selected_options = []
    await session_mgr.save_session(session)

    question = await get_question_fn(next_kc)
    if question:
        session.current_question_id = question.id
        await session_mgr.save_session(session)
        return f"✅ Benar!\n\nSoal berikutnya:\n{format_question(question)}"
    return "✅ Benar! Tidak ada soal berikutnya."


async def _handle_feedback(session, engine, feedback_gen, verification, session_mgr, question, get_question_fn):
    """Handle feedback phase after 3 wrong answers."""
    dominant_id, pattern = engine.classify_misconception_pattern(session.selected_options)
    feedback = await feedback_gen.get_feedback(question.id, dominant_id)
    feedback_msg = FeedbackGenerator.format_feedback_message(feedback)

    # Try to get verification question
    verif_q = await verification.select_verification_question(
        session.current_kc_id, dominant_id, question.id
    )
    if verif_q:
        session.flow_phase = FlowPhase.VERIFICATION
        session.current_question_id = verif_q.id
        session.attempt_count = 0
        await session_mgr.save_session(session)
        return f"❌ Jawaban salah.\n\n{feedback_msg}\n\nSoal verifikasi:\n{format_question(verif_q)}"

    # No verification question — mark needs_review, move on
    logger.warning(f"No verification Q for kc={session.current_kc_id}, misconception={dominant_id}")
    next_kc = await engine.get_next_kc(session.student_id, session.current_kc_id)
    if next_kc is None:
        session.flow_phase = FlowPhase.COMPLETED
        await session_mgr.save_session(session)
        return f"❌ Jawaban salah.\n\n{feedback_msg}\n\n🎉 Assessment selesai."

    session.current_kc_id = next_kc
    session.current_question_id = None
    session.attempt_count = 0
    session.flow_phase = FlowPhase.QUESTION
    session.selected_options = []
    await session_mgr.save_session(session)
    next_q = await get_question_fn(next_kc)
    if next_q:
        session.current_question_id = next_q.id
        await session_mgr.save_session(session)
        return f"❌ Jawaban salah.\n\n{feedback_msg}\n\nSoal berikutnya:\n{format_question(next_q)}"
    return f"❌ Jawaban salah.\n\n{feedback_msg}"


async def _handle_verification(option, session, session_mgr, engine, verification, get_question_fn, question):
    """Handle verification phase — exactly 1 attempt."""
    is_correct = option == question.correct_option
    dominant_id = ""
    if session.selected_options:
        dominant_id = session.selected_options[-1].get("misconception_id", "")

    status = await verification.process_verification_answer(
        session.student_id, session.current_kc_id, question, option, dominant_id
    )

    next_kc = await engine.get_next_kc(session.student_id, session.current_kc_id)
    if next_kc is None:
        session.flow_phase = FlowPhase.COMPLETED
        await session_mgr.save_session(session)
        if is_correct:
            return "✅ Selamat sudah mahir! 🎉 Assessment selesai."
        return "❌ Jawaban salah. Materi ini perlu dipelajari kembali. 🎉 Assessment selesai."

    session.current_kc_id = next_kc
    session.current_question_id = None
    session.attempt_count = 0
    session.flow_phase = FlowPhase.QUESTION
    session.selected_options = []
    await session_mgr.save_session(session)

    next_q = await get_question_fn(next_kc)
    if next_q:
        session.current_question_id = next_q.id
        await session_mgr.save_session(session)

    if is_correct:
        prefix = "✅ Selamat sudah mahir!"
    else:
        prefix = "❌ Jawaban salah. Materi ini perlu dipelajari kembali."

    if next_q:
        return f"{prefix}\n\nSoal berikutnya:\n{format_question(next_q)}"
    return prefix

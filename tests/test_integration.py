# Feature: option-tracing-chatbot - Integration tests for full conversation flow
import pytest

from engine.option_tracing import OptionTracingEngine
from feedback.generator import FeedbackGenerator
from feedback.verification import VerificationSelector
from models import FlowPhase, FeedbackContent, Question, SessionState
from server.flow import process_message
from session.manager import SessionManager


class FakeRedis:
    def __init__(self):
        self._store = {}

    async def hset(self, key, mapping=None):
        self._store[key] = mapping

    async def hgetall(self, key):
        return self._store.get(key)

    async def expire(self, key, ttl):
        pass


class FakeSessionMgr(SessionManager):
    def __init__(self):
        self._sessions = {}

    async def get_session(self, student_id):
        return self._sessions.get(student_id)

    async def save_session(self, state):
        self._sessions[state.student_id] = state

    async def increment_attempt(self, state):
        state.attempt_count += 1
        if state.attempt_count >= 3:
            state.flow_phase = FlowPhase.FEEDBACK
        else:
            state.flow_phase = FlowPhase.RETRY
        self._sessions[state.student_id] = state
        return state


class FakeEngine:
    def __init__(self, kc_sequence):
        self._kcs = kc_sequence
        self._idx = 0

    async def get_next_kc(self, student_id, current_kc_id):
        # Find next KC after current
        try:
            idx = self._kcs.index(current_kc_id)
            if idx + 1 < len(self._kcs):
                return self._kcs[idx + 1]
        except ValueError:
            if self._kcs:
                return self._kcs[0]
        return None

    def classify_misconception_pattern(self, opts):
        return ("m1", "consistent")


class FakeFeedbackGen:
    async def get_feedback(self, question_id, misconception_id):
        return FeedbackContent(
            misconception_name="Test Misconception",
            misconception_description="Student adds instead of multiplies",
            why_incorrect="Addition is wrong here",
            correct_method="Use multiplication",
            is_generic=False,
        )


class FakeVerification:
    def __init__(self, has_question=True):
        self._has_q = has_question

    async def select_verification_question(self, kc_id, misconception_id, original_q_id):
        if not self._has_q:
            return None
        return Question(
            id="vq1", kc_id=kc_id, question_text="Verification Q?",
            correct_option="B", option_a="1", option_b="2", option_c="3", option_d="4",
            distractor_map={"A": misconception_id, "C": misconception_id, "D": misconception_id},
            is_verification=True, target_misconception_id=misconception_id,
        )

    async def process_verification_answer(self, student_id, kc_id, question, selected, misconception):
        return "mastered" if selected == question.correct_option else "needs_review"


QUESTIONS = {
    "kc1": Question(id="q1", kc_id="kc1", question_text="2+2=?", correct_option="A",
                    option_a="4", option_b="3", option_c="5", option_d="6",
                    distractor_map={"B": "m1", "C": "m2", "D": "m3"}),
    "kc2": Question(id="q2", kc_id="kc2", question_text="3*3=?", correct_option="C",
                    option_a="6", option_b="7", option_c="9", option_d="12",
                    distractor_map={"A": "m4", "B": "m5", "D": "m6"}),
}


VERIFICATION_Q = Question(
    id="vq1", kc_id="kc1", question_text="Verification Q?",
    correct_option="B", option_a="1", option_b="2", option_c="3", option_d="4",
    distractor_map={"A": "m1", "C": "m1", "D": "m1"},
    is_verification=True, target_misconception_id="m1",
)


async def get_question(id_or_kc):
    if id_or_kc == "vq1":
        return VERIFICATION_Q
    if id_or_kc in QUESTIONS:
        return QUESTIONS[id_or_kc]
    for q in QUESTIONS.values():
        if q.id == id_or_kc:
            return q
    return None


@pytest.mark.asyncio
async def test_full_flow_correct_answers():
    """Question -> correct -> next KC -> correct -> COMPLETED."""
    mgr = FakeSessionMgr()
    engine = FakeEngine(["kc1", "kc2"])
    feedback = FakeFeedbackGen()
    verif = FakeVerification()

    # First message — new student, gets first question presented
    r1 = await process_message("A", "student1", mgr, engine, feedback, verif, get_question)
    assert "Benar" in r1
    # Should advance to kc2
    assert mgr._sessions["student1"].current_kc_id == "kc2"

    # Second message — correct on kc2
    r2 = await process_message("C", "student1", mgr, engine, feedback, verif, get_question)
    assert "Selamat" in r2 or "selesai" in r2.lower()
    assert mgr._sessions["student1"].flow_phase == FlowPhase.COMPLETED


@pytest.mark.asyncio
async def test_full_flow_3_wrong_triggers_feedback_and_verification():
    """Question -> 3 wrong -> feedback -> verification question presented."""
    mgr = FakeSessionMgr()
    engine = FakeEngine(["kc1", "kc2"])
    feedback = FakeFeedbackGen()
    verif = FakeVerification(has_question=True)

    # First wrong
    r1 = await process_message("B", "student1", mgr, engine, feedback, verif, get_question)
    assert "salah" in r1.lower()
    assert "kesempatan" in r1

    # Second wrong
    r2 = await process_message("C", "student1", mgr, engine, feedback, verif, get_question)
    assert "salah" in r2.lower()

    # Third wrong -> feedback + verification
    r3 = await process_message("D", "student1", mgr, engine, feedback, verif, get_question)
    assert "Feedback" in r3
    assert "Miskonsepsi" in r3 or "Misconception" in r3 or "Test Misconception" in r3
    assert "Verification" in r3 or "verifikasi" in r3.lower() or "Soal" in r3
    assert mgr._sessions["student1"].flow_phase == FlowPhase.VERIFICATION


@pytest.mark.asyncio
async def test_full_flow_verification_correct_advances():
    """After verification correct -> mastered, advance to next KC."""
    mgr = FakeSessionMgr()
    engine = FakeEngine(["kc1", "kc2"])
    feedback = FakeFeedbackGen()
    verif = FakeVerification(has_question=True)

    # 3 wrong to get to verification
    await process_message("B", "student1", mgr, engine, feedback, verif, get_question)
    await process_message("C", "student1", mgr, engine, feedback, verif, get_question)
    await process_message("D", "student1", mgr, engine, feedback, verif, get_question)

    # Verification correct (B is correct for verification question)
    r = await process_message("B", "student1", mgr, engine, feedback, verif, get_question)
    assert "mahir" in r.lower() or "Selamat" in r
    assert mgr._sessions["student1"].current_kc_id == "kc2"


@pytest.mark.asyncio
async def test_invalid_input_reprompts():
    """Invalid input doesn't change state."""
    mgr = FakeSessionMgr()
    engine = FakeEngine(["kc1", "kc2"])
    feedback = FakeFeedbackGen()
    verif = FakeVerification()

    # Invalid input
    r = await process_message("X", "student1", mgr, engine, feedback, verif, get_question)
    assert "A, B, C, atau D" in r

# Feature: option-tracing-chatbot, Property 4: Correct answer advances to next KC
import pytest
from hypothesis import given, strategies as st

from models import FlowPhase, Question, SessionState
from server.flow import process_message

valid_options = st.sampled_from(["A", "B", "C", "D"])


class FakeRedis:
    async def hset(self, *a, **kw): pass
    async def expire(self, *a, **kw): pass
    async def hgetall(self, key): return None


class FakeSessionMgr:
    def __init__(self, session):
        self._session = session
        self.saved = None

    async def get_session(self, student_id):
        return self._session

    async def save_session(self, state):
        self.saved = state

    async def increment_attempt(self, state):
        state.attempt_count += 1
        state.flow_phase = FlowPhase.FEEDBACK if state.attempt_count >= 3 else FlowPhase.RETRY
        return state


class FakeEngine:
    def __init__(self, next_kc):
        self._next_kc = next_kc

    async def get_next_kc(self, student_id, current_kc_id):
        return self._next_kc

    def classify_misconception_pattern(self, opts):
        return ("m1", "varied")


class FakeFeedback:
    pass


class FakeVerification:
    pass


@pytest.mark.asyncio
@given(correct_option=valid_options)
async def test_correct_answer_advances_to_next_kc(correct_option):
    """Submitting correct option transitions to next KC."""
    question = Question(
        id="q1", kc_id="kc1", question_text="Q?",
        correct_option=correct_option,
        option_a="a", option_b="b", option_c="c", option_d="d",
        distractor_map={o: f"m{o}" for o in "ABCD" if o != correct_option},
    )
    session = SessionState(
        student_id="s1", current_kc_id="kc1", current_question_id="q1",
        attempt_count=0, flow_phase=FlowPhase.QUESTION,
        selected_options=[], session_id="sess1",
    )
    mgr = FakeSessionMgr(session)
    engine = FakeEngine(next_kc="kc2")

    async def get_q(id_or_kc):
        return question

    response = await process_message(
        text=correct_option,
        student_id="s1",
        session_mgr=mgr,
        engine=engine,
        feedback_gen=FakeFeedback(),
        verification=FakeVerification(),
        get_question_fn=get_q,
    )
    assert "✅" in response or "Benar" in response
    assert mgr.saved is not None
    assert mgr.saved.current_kc_id == "kc2"


@pytest.mark.asyncio
async def test_correct_answer_completes_when_no_kcs_left():
    """When no more KCs, submitting correct option transitions to COMPLETED."""
    question = Question(
        id="q1", kc_id="kc3", question_text="Q?",
        correct_option="A",
        option_a="a", option_b="b", option_c="c", option_d="d",
        distractor_map={"B": "m1", "C": "m2", "D": "m3"},
    )
    session = SessionState(
        student_id="s1", current_kc_id="kc3", current_question_id="q1",
        attempt_count=0, flow_phase=FlowPhase.QUESTION,
        selected_options=[], session_id="sess1",
    )
    mgr = FakeSessionMgr(session)
    engine = FakeEngine(next_kc=None)

    async def get_q(id_or_kc):
        return question

    response = await process_message(
        text="A", student_id="s1", session_mgr=mgr,
        engine=engine, feedback_gen=FakeFeedback(),
        verification=FakeVerification(), get_question_fn=get_q,
    )
    assert "Selamat" in response or "selesai" in response.lower()
    assert mgr.saved.flow_phase == FlowPhase.COMPLETED

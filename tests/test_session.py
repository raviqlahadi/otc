# Feature: option-tracing-chatbot
import copy

import pytest
from hypothesis import given, strategies as st

from models import FlowPhase, SessionState
from session.manager import SessionManager

valid_options = st.sampled_from(["A", "B", "C", "D"])

session_states = st.builds(
    SessionState,
    student_id=st.text(min_size=1, max_size=20, alphabet=st.characters(categories=("L", "Nd"))),
    current_kc_id=st.text(min_size=1, max_size=20, alphabet=st.characters(categories=("L", "Nd"))),
    current_question_id=st.one_of(st.none(), st.text(min_size=1, max_size=20, alphabet=st.characters(categories=("L", "Nd")))),
    attempt_count=st.integers(min_value=0, max_value=3),
    flow_phase=st.sampled_from(list(FlowPhase)),
    selected_options=st.lists(
        st.fixed_dictionaries({
            "attempt": st.integers(min_value=1, max_value=3),
            "option": valid_options,
            "misconception_id": st.text(min_size=1, max_size=20, alphabet=st.characters(categories=("L", "Nd"))),
        }),
        max_size=3,
    ),
    session_id=st.text(min_size=1, max_size=36, alphabet=st.characters(categories=("L", "Nd"))),
)


# Property 17: Session state serialization round-trip
@given(state=session_states)
def test_session_serialize_deserialize_roundtrip(state: SessionState):
    """Any valid SessionState survives serialize -> deserialize unchanged."""
    mgr = SessionManager.__new__(SessionManager)
    serialized = mgr._serialize(state)
    restored = mgr._deserialize(serialized)
    assert restored.student_id == state.student_id
    assert restored.current_kc_id == state.current_kc_id
    assert restored.current_question_id == state.current_question_id
    assert restored.attempt_count == state.attempt_count
    assert restored.flow_phase == state.flow_phase
    assert restored.selected_options == state.selected_options
    assert restored.session_id == state.session_id


# Property 9: Attempt counting and feedback trigger
@given(attempt_count=st.integers(min_value=0, max_value=2))
@pytest.mark.asyncio
async def test_attempt_counting_and_feedback_trigger(attempt_count: int):
    """attempt_count increments by 1; at 3 total, phase -> FEEDBACK."""

    class FakeRedis:
        async def hset(self, *a, **kw): pass
        async def expire(self, *a, **kw): pass

    state = SessionState(
        student_id="s1", current_kc_id="kc1", current_question_id="q1",
        attempt_count=attempt_count, flow_phase=FlowPhase.QUESTION,
        selected_options=[], session_id="sess1",
    )
    mgr = SessionManager(FakeRedis(), None)
    result = await mgr.increment_attempt(state)
    assert result.attempt_count == attempt_count + 1
    if result.attempt_count >= 3:
        assert result.flow_phase == FlowPhase.FEEDBACK
    else:
        assert result.flow_phase == FlowPhase.RETRY


# Property 10: Session context preservation during retry
@given(
    option=valid_options,
    misconception_id=st.text(min_size=1, max_size=10, alphabet=st.characters(categories=("L", "Nd"))),
)
@pytest.mark.asyncio
async def test_session_context_preserved_during_retry(option, misconception_id):
    """During retry, question_id preserved, selected_options accumulated, attempt_count updated."""

    class FakeRedis:
        async def hset(self, *a, **kw): pass
        async def expire(self, *a, **kw): pass

    state = SessionState(
        student_id="s1", current_kc_id="kc1", current_question_id="q1",
        attempt_count=0, flow_phase=FlowPhase.QUESTION,
        selected_options=[], session_id="sess1",
    )
    original_question_id = state.current_question_id

    # Simulate adding selected option and incrementing
    state.selected_options.append({"attempt": 1, "option": option, "misconception_id": misconception_id})
    mgr = SessionManager(FakeRedis(), None)
    result = await mgr.increment_attempt(state)

    assert result.current_question_id == original_question_id
    assert len(result.selected_options) == 1
    assert result.selected_options[0]["option"] == option
    assert result.attempt_count == 1

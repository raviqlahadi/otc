# Feature: option-tracing-chatbot
from hypothesis import given, strategies as st, assume

from engine.option_tracing import OptionTracingEngine
from models import BKTParams, StudentMastery

# Strategies
bkt_params = st.builds(
    BKTParams,
    p_l0=st.floats(min_value=0.01, max_value=0.99),
    p_guess=st.floats(min_value=0.01, max_value=0.49),
    p_slip=st.floats(min_value=0.01, max_value=0.49),
    p_transit=st.floats(min_value=0.01, max_value=0.99),
)

mastery_states = st.builds(
    StudentMastery,
    student_id=st.just("s1"),
    kc_id=st.just("kc1"),
    p_mastery=st.floats(min_value=0.0, max_value=1.0),
    p_transition=st.floats(min_value=0.0, max_value=1.0),
)


# Property 14: BKT probability bounds invariant
@given(mastery=mastery_states, params=bkt_params, correct=st.booleans())
def test_bkt_probability_bounds_single(mastery, params, correct):
    """After one update, P(mastery) remains in [0.0, 1.0]."""
    engine = OptionTracingEngine.__new__(OptionTracingEngine)
    result = engine.compute_mastery_update(mastery, correct, params)
    assert 0.0 <= result.p_mastery <= 1.0


@given(
    params=bkt_params,
    interactions=st.lists(st.booleans(), min_size=1, max_size=10),
)
def test_bkt_probability_bounds_sequence(params, interactions):
    """For any sequence of interactions, P(mastery) remains in [0.0, 1.0]."""
    engine = OptionTracingEngine.__new__(OptionTracingEngine)
    mastery = StudentMastery(student_id="s1", kc_id="kc1", p_mastery=params.p_l0, p_transition=params.p_transit)
    for correct in interactions:
        mastery = engine.compute_mastery_update(mastery, correct, params)
        assert 0.0 <= mastery.p_mastery <= 1.0


# Property 16: New student initialization values
@given(params=bkt_params)
def test_new_student_initialization(params):
    """New student: P(mastery)=P(L₀), P(transition)=initial rate."""
    mastery = StudentMastery(
        student_id="new", kc_id="kc1",
        p_mastery=params.p_l0,
        p_transition=params.p_transit,
    )
    assert mastery.p_mastery == params.p_l0
    assert mastery.p_transition == params.p_transit
    assert mastery.misconception_probs == {}

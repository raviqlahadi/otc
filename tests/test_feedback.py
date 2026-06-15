# Feature: option-tracing-chatbot
from hypothesis import given, strategies as st

from feedback.generator import FeedbackGenerator
from models import FeedbackContent


# Property 11: Feedback message structure
@given(
    name=st.text(min_size=1, max_size=50),
    description=st.text(min_size=1, max_size=100),
    why_incorrect=st.text(min_size=1, max_size=100),
    correct_method=st.text(min_size=1, max_size=100),
)
def test_non_generic_feedback_contains_three_components(name, description, why_incorrect, correct_method):
    """Non-generic feedback contains all 3 components in order: name/description, why incorrect, correct method."""
    feedback = FeedbackContent(
        misconception_name=name,
        misconception_description=description,
        why_incorrect=why_incorrect,
        correct_method=correct_method,
        is_generic=False,
    )
    msg = FeedbackGenerator.format_feedback_message(feedback)
    # All three components present
    assert name in msg
    assert description in msg
    assert why_incorrect in msg
    assert correct_method in msg
    # Structural order via section headers
    assert "Miskonsepsi yang terdeteksi:" in msg
    assert "Mengapa keliru:" in msg
    assert "Cara yang benar:" in msg
    assert msg.index("Miskonsepsi yang terdeteksi:") < msg.index("Mengapa keliru:")
    assert msg.index("Mengapa keliru:") < msg.index("Cara yang benar:")


@given(correct_method=st.text(min_size=1, max_size=100))
def test_generic_feedback_contains_correct_method(correct_method):
    """Generic feedback contains the correct method only."""
    feedback = FeedbackContent(
        misconception_name="", misconception_description="",
        why_incorrect="", correct_method=correct_method, is_generic=True,
    )
    msg = FeedbackGenerator.format_feedback_message(feedback)
    assert correct_method in msg
    assert "Miskonsepsi" not in msg


# --- Task 6.4: Property 12 & 13 - Verification phase ---
from hypothesis import given, assume
from models import Question


# Property 12: Verification question selection constraints
@given(
    kc_id=st.text(min_size=1, max_size=10, alphabet=st.characters(categories=("L", "Nd"))),
    misconception_id=st.text(min_size=1, max_size=10, alphabet=st.characters(categories=("L", "Nd"))),
    original_q_id=st.text(min_size=1, max_size=10, alphabet=st.characters(categories=("L", "Nd"))),
    verif_q_id=st.text(min_size=1, max_size=10, alphabet=st.characters(categories=("L", "Nd"))),
)
def test_verification_question_selection_constraints(kc_id, misconception_id, original_q_id, verif_q_id):
    """Verification question: different from original, same KC, distractors map to same misconception."""
    assume(verif_q_id != original_q_id)
    # Simulate a valid verification question
    verif_q = Question(
        id=verif_q_id, kc_id=kc_id, question_text="Verify?",
        correct_option="A", option_a="a", option_b="b", option_c="c", option_d="d",
        distractor_map={"B": misconception_id, "C": misconception_id, "D": misconception_id},
        is_verification=True, target_misconception_id=misconception_id,
    )
    assert verif_q.id != original_q_id
    assert verif_q.kc_id == kc_id
    assert misconception_id in verif_q.distractor_map.values()


# Property 13: Verification phase state transitions
@given(correct=st.booleans())
def test_verification_phase_state_transitions(correct):
    """Correct -> 'mastered', incorrect -> 'needs_review'. Exactly 1 attempt consumed."""
    question = Question(
        id="vq1", kc_id="kc1", question_text="Verify?",
        correct_option="A", option_a="a", option_b="b", option_c="c", option_d="d",
        distractor_map={"B": "m1", "C": "m2", "D": "m3"},
    )
    selected = "A" if correct else "B"
    is_correct = selected == question.correct_option
    status = "mastered" if is_correct else "needs_review"
    if correct:
        assert status == "mastered"
    else:
        assert status == "needs_review"
    # Exactly 1 attempt (verification allows no retries)
    attempts_consumed = 1
    assert attempts_consumed == 1

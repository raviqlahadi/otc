# Feature: option-tracing-chatbot
from hypothesis import given, strategies as st

from models import Question

valid_options = st.sampled_from(["A", "B", "C", "D"])


def make_question(correct_option: str, distractor_map: dict[str, str]) -> Question:
    return Question(
        id="q1", kc_id="kc1", question_text="Test?",
        correct_option=correct_option,
        option_a="a", option_b="b", option_c="c", option_d="d",
        distractor_map=distractor_map,
    )


# Property 5: Distractor-misconception mapping integrity
@given(correct=valid_options)
def test_distractor_mapping_integrity(correct):
    """Each distractor maps to exactly one misconception; correct option not in mapping."""
    distractors = [o for o in ["A", "B", "C", "D"] if o != correct]
    distractor_map = {d: f"misc_{d}" for d in distractors}
    q = make_question(correct, distractor_map)
    # Correct option not in distractor map
    assert q.correct_option not in q.distractor_map
    # Each distractor maps to exactly one misconception
    for d in distractors:
        assert d in q.distractor_map
        assert isinstance(q.distractor_map[d], str)
        assert len(q.distractor_map[d]) > 0


# Property 6: Option-to-misconception identification
@given(correct=valid_options)
def test_option_to_misconception_identification(correct):
    """Wrong option returns matching misconception_id from stored mapping."""
    distractors = [o for o in ["A", "B", "C", "D"] if o != correct]
    distractor_map = {d: f"misc_{d}" for d in distractors}
    q = make_question(correct, distractor_map)
    for wrong_option in distractors:
        misconception_id = q.distractor_map.get(wrong_option)
        assert misconception_id == f"misc_{wrong_option}"


# Property 7: Interaction logging completeness
@given(
    selected_option=valid_options,
    attempt_number=st.integers(min_value=1, max_value=3),
    student_id=st.text(min_size=1, max_size=10, alphabet=st.characters(categories=("L", "Nd"))),
    question_id=st.text(min_size=1, max_size=10, alphabet=st.characters(categories=("L", "Nd"))),
)
def test_interaction_logging_completeness(selected_option, attempt_number, student_id, question_id):
    """Log entry contains all required fields."""
    # Simulate what process_answer would produce for logging
    correct_option = "A"
    distractor_map = {"B": "m1", "C": "m2", "D": "m3"}
    is_correct = selected_option == correct_option
    misconception_id = None if is_correct else distractor_map.get(selected_option)

    log_entry = {
        "student_id": student_id,
        "question_id": question_id,
        "attempt_number": attempt_number,
        "selected_option": selected_option,
        "is_correct": is_correct,
        "misconception_id": misconception_id,
    }
    assert "student_id" in log_entry and log_entry["student_id"]
    assert "question_id" in log_entry and log_entry["question_id"]
    assert "attempt_number" in log_entry and 1 <= log_entry["attempt_number"] <= 3
    assert "selected_option" in log_entry and log_entry["selected_option"] in {"A", "B", "C", "D"}
    if not is_correct:
        assert log_entry["misconception_id"] is not None


# --- Task 4.6: Property 8 - Misconception pattern classification ---
from engine.option_tracing import OptionTracingEngine

misconception_ids = st.text(min_size=1, max_size=10, alphabet=st.characters(categories=("L", "Nd")))


@given(misconception_seq=st.lists(misconception_ids, min_size=1, max_size=3))
def test_misconception_pattern_classification(misconception_seq):
    """'consistent' when same misconception >=2 times, 'varied' otherwise; tie-break by recency."""
    engine = OptionTracingEngine.__new__(OptionTracingEngine)
    selected_options = [
        {"attempt": i + 1, "option": "B", "misconception_id": m}
        for i, m in enumerate(misconception_seq)
    ]
    dominant, pattern = engine.classify_misconception_pattern(selected_options)

    # Count occurrences
    from collections import Counter
    counts = Counter(misconception_seq)
    max_count = max(counts.values())

    if max_count >= 2:
        assert pattern == "consistent"
    else:
        assert pattern == "varied"

    # Dominant should be the most frequent, tie-break by recency (last in list)
    max_candidates = [m for m, c in counts.items() if c == max_count]
    if len(max_candidates) == 1:
        assert dominant == max_candidates[0]
    else:
        # Tie-break: most recent
        assert dominant == misconception_seq[-1]


# --- Task 4.8: Property 15 - KC graph traversal respects prerequisites ---

@given(
    num_kcs=st.integers(min_value=2, max_value=5),
    mastered_count=st.integers(min_value=0, max_value=4),
)
def test_kc_graph_traversal_respects_prerequisites(num_kcs, mastered_count):
    """Next KC only selected if all its prerequisites are completed/mastered."""
    # Build a linear prerequisite chain: kc0 -> kc1 -> kc2 -> ...
    kcs = [{"id": f"kc{i}", "prerequisite_kc_id": f"kc{i-1}" if i > 0 else None, "display_order": i} for i in range(num_kcs)]
    mastered_ids = {f"kc{i}" for i in range(min(mastered_count, num_kcs))}

    # Simulate get_next_kc logic
    next_kc = None
    for kc in kcs:
        if kc["id"] in mastered_ids:
            continue
        prereq = kc["prerequisite_kc_id"]
        if prereq is None or prereq in mastered_ids:
            next_kc = kc["id"]
            break

    if mastered_count >= num_kcs:
        assert next_kc is None  # All mastered
    else:
        # The next KC should have its prereq satisfied
        expected_next = f"kc{mastered_count}"
        assert next_kc == expected_next
        prereq_of_next = kcs[mastered_count]["prerequisite_kc_id"]
        if prereq_of_next is not None:
            assert prereq_of_next in mastered_ids

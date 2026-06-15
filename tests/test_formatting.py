# Feature: option-tracing-chatbot
from hypothesis import given, strategies as st

from models import Question
from server.formatting import format_question

valid_options = st.sampled_from(["A", "B", "C", "D"])


# Property 1: Question formatting structure
@given(
    stem=st.text(min_size=1, max_size=200, alphabet=st.characters(blacklist_characters="\n\r")),
    opt_a=st.text(min_size=1, max_size=50, alphabet=st.characters(blacklist_characters="\n\r")),
    opt_b=st.text(min_size=1, max_size=50, alphabet=st.characters(blacklist_characters="\n\r")),
    opt_c=st.text(min_size=1, max_size=50, alphabet=st.characters(blacklist_characters="\n\r")),
    opt_d=st.text(min_size=1, max_size=50, alphabet=st.characters(blacklist_characters="\n\r")),
    correct=valid_options,
)
def test_question_formatting_structure(stem, opt_a, opt_b, opt_c, opt_d, correct):
    """Formatted output contains stem + exactly 4 labeled options (A, B, C, D) on separate lines."""
    q = Question(
        id="q1", kc_id="kc1", question_text=stem,
        correct_option=correct,
        option_a=opt_a, option_b=opt_b, option_c=opt_c, option_d=opt_d,
    )
    formatted = format_question(q)
    lines = formatted.split("\n")
    assert lines[0] == stem
    assert lines[1].startswith("A. ")
    assert lines[2].startswith("B. ")
    assert lines[3].startswith("C. ")
    assert lines[4].startswith("D. ")
    assert len(lines) == 5

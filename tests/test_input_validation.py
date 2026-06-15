# Feature: option-tracing-chatbot
from hypothesis import given, strategies as st

from validation.input_validator import validate_answer

# Strategy: valid option with arbitrary whitespace and case
valid_input_strings = st.builds(
    lambda ws_before, letter, use_upper, ws_after: f"{ws_before}{letter if use_upper else letter.lower()}{ws_after}",
    ws_before=st.text(alphabet=" \t\n", max_size=3),
    letter=st.sampled_from(["A", "B", "C", "D"]),
    use_upper=st.booleans(),
    ws_after=st.text(alphabet=" \t\n", max_size=3),
)

# Strategy: invalid inputs
invalid_inputs = st.text(min_size=0, max_size=50).filter(
    lambda s: s.strip().upper() not in {"A", "B", "C", "D"}
)


# Property 2: Valid input acceptance
@given(text=valid_input_strings)
def test_valid_input_accepted_and_normalized(text: str):
    """For any A-D with whitespace/case variation, validator accepts and returns uppercase."""
    valid, option = validate_answer(text)
    assert valid is True
    assert option in {"A", "B", "C", "D"}
    assert option == text.strip().upper()


# Property 3: Invalid input rejection
@given(text=invalid_inputs)
def test_invalid_input_rejected(text: str):
    """For any non-A/B/C/D string, validator rejects."""
    valid, option = validate_answer(text)
    assert valid is False
    assert option is None

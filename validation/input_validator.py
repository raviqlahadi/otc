VALID_OPTIONS = {"A", "B", "C", "D"}


def validate_answer(text: str) -> tuple[bool, str | None]:
    """Validate and normalize student answer. Accepts A-D, case-insensitive, strips whitespace."""
    cleaned = text.strip().upper()
    if cleaned in VALID_OPTIONS:
        return (True, cleaned)
    return (False, None)

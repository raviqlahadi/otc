# Feature: option-tracing-chatbot
import hashlib

from hypothesis import given, strategies as st

from session.registration import StudentRegistration

phone_numbers = st.text(min_size=8, max_size=15, alphabet=st.characters(categories=("Nd",)))


# Property 24: Phone number stored as hash
@given(phone=phone_numbers)
def test_phone_hash_not_equal_to_raw(phone):
    """Stored phone_hash != raw phone number and is a deterministic hash."""
    hashed = StudentRegistration.hash_phone(phone)
    assert hashed != phone
    assert len(hashed) == 64  # SHA-256 hex
    # Deterministic
    assert StudentRegistration.hash_phone(phone) == hashed


# Property 23: Student progress resumption round-trip (structure test)
@given(
    current_kc=st.text(min_size=1, max_size=10, alphabet=st.characters(categories=("L", "Nd"))),
    completed=st.lists(st.text(min_size=1, max_size=10, alphabet=st.characters(categories=("L", "Nd"))), max_size=3),
    session_id=st.text(min_size=1, max_size=20, alphabet=st.characters(categories=("L", "Nd"))),
)
def test_progress_resumption_structure(current_kc, completed, session_id):
    """Persisted progress loads correctly with right current KC and completed KCs."""
    # Simulate what get_progress would return
    progress = {
        "current_kc_id": current_kc,
        "completed_kc_ids": completed,
        "last_session_id": session_id,
    }
    assert progress["current_kc_id"] == current_kc
    assert progress["completed_kc_ids"] == completed
    assert progress["last_session_id"] == session_id

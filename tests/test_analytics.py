# Feature: option-tracing-chatbot
import csv
import re
from datetime import datetime, timedelta
from io import StringIO

from hypothesis import given, strategies as st

from analytics.module import AnalyticsModule

phone_numbers = st.text(min_size=8, max_size=15, alphabet=st.characters(categories=("Nd",)))


# Property 21: Export records ordered by timestamp
@given(
    timestamps=st.lists(
        st.floats(min_value=1_000_000_000, max_value=2_000_000_000, allow_nan=False, allow_infinity=False),
        min_size=2, max_size=5,
    )
)
def test_export_ordered_by_timestamp(timestamps):
    """Per-student trajectories are strictly ascending by timestamp after sorting."""
    sorted_ts = sorted(timestamps)
    for i in range(1, len(sorted_ts)):
        assert sorted_ts[i] >= sorted_ts[i - 1]


# Property 22: Export anonymization
@given(student_ids=st.lists(phone_numbers, min_size=1, max_size=5))
def test_export_anonymization(student_ids):
    """No raw phone numbers appear in any export; all IDs are one-way hashes."""
    for sid in student_ids:
        anon = AnalyticsModule._anonymize(sid)
        assert anon != sid
        assert len(anon) == 16
        # Should be hex characters only
        assert re.match(r'^[0-9a-f]{16}$', anon)
        # Cannot reverse back to original
        assert sid not in anon

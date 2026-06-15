# Feature: option-tracing-chatbot
import hashlib
import hmac

import pytest
from hypothesis import given, strategies as st

from messaging.whatsapp_adapter import WhatsAppAdapter
from models import Platform

ADAPTER = WhatsAppAdapter("123", "token", "verify", "test_secret")


def make_payload(sender: str, text: str, msg_id: str, ts: str = "1700000000"):
    return {
        "entry": [{"changes": [{"value": {
            "messages": [{"from": sender, "text": {"body": text}, "id": msg_id, "timestamp": ts}],
            "contacts": [{"profile": {"name": "Test"}, "wa_id": sender}],
        }}]}]
    }


# Property 18: Webhook signature validation
@given(body=st.binary(min_size=1, max_size=200))
def test_webhook_valid_signature_accepted(body: bytes):
    """Valid HMAC-SHA256 signature is accepted."""
    sig = "sha256=" + hmac.new(b"test_secret", body, hashlib.sha256).hexdigest()
    assert ADAPTER.validate_webhook({"x-hub-signature-256": sig}, body) is True


@given(body=st.binary(min_size=1, max_size=200))
def test_webhook_invalid_signature_rejected(body: bytes):
    """Invalid signature is rejected."""
    assert ADAPTER.validate_webhook({"x-hub-signature-256": "sha256=bad"}, body) is False


@given(body=st.binary(min_size=1, max_size=200))
def test_webhook_missing_signature_rejected(body: bytes):
    """Missing signature header is rejected."""
    assert ADAPTER.validate_webhook({}, body) is False


# Property 20: Message normalization
@given(
    sender=st.text(min_size=1, max_size=20, alphabet=st.characters(categories=("Nd",))),
    text=st.text(min_size=1, max_size=100),
    msg_id=st.text(min_size=1, max_size=30, alphabet=st.characters(categories=("L", "Nd"))),
)
@pytest.mark.asyncio
async def test_message_normalization_produces_valid_message(sender, text, msg_id):
    """Valid payloads produce NormalizedMessage with non-empty sender_id, text, and correct platform."""
    payload = make_payload(sender, text, msg_id)
    result = await ADAPTER.normalize(payload)
    assert result is not None
    assert result.sender_id == sender
    assert result.message_text == text
    assert result.platform == Platform.WHATSAPP


@pytest.mark.asyncio
async def test_normalization_returns_none_for_status_update():
    """Non-message events (status updates) return None."""
    payload = {"entry": [{"changes": [{"value": {"statuses": [{"status": "read"}]}}]}]}
    result = await ADAPTER.normalize(payload)
    assert result is None

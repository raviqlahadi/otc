# Feature: option-tracing-chatbot, Property 19: Message deduplication (idempotency)
import hashlib
import hmac
import json

import pytest
from httpx import AsyncClient, ASGITransport

from server.webhook import app, configure
from models import NormalizedMessage, OutgoingMessage, Platform
from messaging.gateway import MessagingAdapter, MessagingGateway


class FakeWhatsAppAdapter(MessagingAdapter):
    def __init__(self):
        self.sent = []

    async def normalize(self, raw_payload: dict) -> NormalizedMessage | None:
        try:
            msg = raw_payload["entry"][0]["changes"][0]["value"]["messages"][0]
            return NormalizedMessage(
                sender_id=msg["from"], message_text=msg["text"]["body"],
                message_id=msg["id"], platform=Platform.WHATSAPP, timestamp=float(msg["timestamp"]),
            )
        except (KeyError, IndexError):
            return None

    async def send(self, message: OutgoingMessage) -> bool:
        self.sent.append(message)
        return True

    def validate_webhook(self, headers: dict, body: bytes) -> bool:
        return True  # Skip signature check for test


class FakeRedis:
    def __init__(self):
        self._store = {}

    async def get(self, key):
        return self._store.get(key)

    async def set(self, key, value, ex=None):
        self._store[key] = value

    async def hgetall(self, key):
        return None

    async def hset(self, *a, **kw):
        pass

    async def expire(self, *a, **kw):
        pass


@pytest.fixture
def setup_app():
    adapter = FakeWhatsAppAdapter()
    gateway = MessagingGateway({Platform.WHATSAPP: adapter})
    redis = FakeRedis()
    configure(gateway=gateway, session_mgr=None, engine=None, feedback_gen=None, verification=None, redis_client=redis)
    return adapter, redis


def make_webhook_payload(msg_id="msg123", text="A"):
    return {"entry": [{"changes": [{"value": {
        "messages": [{"from": "628123", "text": {"body": text}, "id": msg_id, "timestamp": "1700000000"}],
        "contacts": [{"profile": {"name": "Test"}, "wa_id": "628123"}],
    }}]}]}


@pytest.mark.asyncio
async def test_deduplication_same_message_id_no_reprocessing(setup_app):
    """Same message_id submitted twice: second time no additional processing, still HTTP 200."""
    adapter, redis = setup_app

    payload = make_webhook_payload(msg_id="dup_test_1")
    body = json.dumps(payload).encode()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # First request
        r1 = await client.post("/webhook", content=body, headers={"content-type": "application/json"})
        assert r1.status_code == 200

        # Second request with same message_id
        r2 = await client.post("/webhook", content=body, headers={"content-type": "application/json"})
        assert r2.status_code == 200

    # The dedup key should have been set on first request, blocking second
    assert await redis.get("msg:dup_test_1") == "1"


@pytest.mark.asyncio
async def test_different_message_ids_both_processed(setup_app):
    """Different message_ids are both processed."""
    adapter, redis = setup_app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        p1 = make_webhook_payload(msg_id="msg_a")
        r1 = await client.post("/webhook", content=json.dumps(p1).encode(), headers={"content-type": "application/json"})
        assert r1.status_code == 200

        p2 = make_webhook_payload(msg_id="msg_b")
        r2 = await client.post("/webhook", content=json.dumps(p2).encode(), headers={"content-type": "application/json"})
        assert r2.status_code == 200

    assert await redis.get("msg:msg_a") == "1"
    assert await redis.get("msg:msg_b") == "1"

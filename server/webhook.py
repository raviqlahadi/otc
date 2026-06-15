import logging

from fastapi import FastAPI, Request, Response, HTTPException, Query

from config import settings
from models import Platform, OutgoingMessage

logger = logging.getLogger(__name__)

app = FastAPI(title="Option Tracing Chatbot")

# These will be set during startup via dependency injection
_gateway = None
_session_mgr = None
_engine = None
_feedback_gen = None
_verification = None
_redis = None


def configure(gateway, session_mgr, engine, feedback_gen, verification, redis_client):
    global _gateway, _session_mgr, _engine, _feedback_gen, _verification, _redis
    _gateway = gateway
    _session_mgr = session_mgr
    _engine = engine
    _feedback_gen = feedback_gen
    _verification = verification
    _redis = redis_client


@app.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query("", alias="hub.mode"),
    hub_verify_token: str = Query("", alias="hub.verify_token"),
    hub_challenge: str = Query("", alias="hub.challenge"),
):
    """WhatsApp webhook verification endpoint."""
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        return Response(content=hub_challenge, media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook")
async def handle_webhook(request: Request):
    """Process incoming WhatsApp messages."""
    body = await request.body()

    if not _gateway.validate_webhook(Platform.WHATSAPP, dict(request.headers), body):
        raise HTTPException(status_code=403, detail="Invalid signature")

    payload = await request.json()
    message = await _gateway.normalize(Platform.WHATSAPP, payload)

    if message is None:
        return {"status": "ok"}

    # Deduplication
    dedup_key = f"msg:{message.message_id}"
    if _redis:
        already = await _redis.get(dedup_key)
        if already:
            return {"status": "ok"}
        await _redis.set(dedup_key, "1", ex=3600)

    # Process
    try:
        from server.flow import process_message
        response_text = await process_message(
            text=message.message_text,
            student_id=message.sender_id,
            session_mgr=_session_mgr,
            engine=_engine,
            feedback_gen=_feedback_gen,
            verification=_verification,
            get_question_fn=_get_question,
        )
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        response_text = "Maaf, sistem sedang gangguan. Silakan coba lagi nanti."

    await _gateway.send(OutgoingMessage(
        recipient_id=message.sender_id,
        text=response_text,
        platform=message.platform,
    ))
    return {"status": "ok"}


async def _get_question(id_or_kc: str):
    """Load question by ID or by KC (first available)."""
    # This will be wired to actual DB in dependencies
    return None

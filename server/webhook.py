import logging

from fastapi import FastAPI, Request, Response, HTTPException, Query, Depends

from config import settings
from models.messaging import OutgoingMessage, Platform
from server.deps import get_flow_controller, get_gateway, get_redis

logger = logging.getLogger(__name__)

app = FastAPI(title="Option Tracing Chatbot")


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
async def handle_webhook(
    request: Request,
    gateway=Depends(get_gateway),
    flow_controller=Depends(get_flow_controller),
    redis=Depends(get_redis),
):
    """Process incoming WhatsApp messages."""
    body = await request.body()

    if not gateway.validate_webhook(Platform.WHATSAPP, dict(request.headers), body):
        raise HTTPException(status_code=403, detail="Invalid signature")

    payload = await request.json()
    message = await gateway.normalize(Platform.WHATSAPP, payload)

    if message is None:
        return {"status": "ok"}

    # Deduplication
    dedup_key = f"msg:{message.message_id}"
    if redis:
        already = await redis.get(dedup_key)
        if already:
            return {"status": "ok"}
        await redis.set(dedup_key, "1", ex=3600)

    # Process via FlowController
    try:
        response_text = await flow_controller.handle(
            text=message.message_text,
            student_id=message.sender_id,
        )
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        response_text = "Maaf, sistem sedang gangguan. Silakan coba lagi nanti."

    await gateway.send(OutgoingMessage(
        recipient_id=message.sender_id,
        text=response_text,
        platform=message.platform,
    ))
    return {"status": "ok"}

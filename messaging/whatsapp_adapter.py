import hashlib
import hmac

import httpx

from messaging.gateway import MessagingAdapter
from models import NormalizedMessage, OutgoingMessage, Platform


class WhatsAppAdapter(MessagingAdapter):
    def __init__(self, phone_number_id: str, access_token: str, verify_token: str, app_secret: str):
        self._phone_number_id = phone_number_id
        self._access_token = access_token
        self.verify_token = verify_token
        self._app_secret = app_secret
        self._api_base = f"https://graph.facebook.com/v18.0/{phone_number_id}/messages"

    async def normalize(self, raw_payload: dict) -> NormalizedMessage | None:
        try:
            entry = raw_payload["entry"][0]
            change = entry["changes"][0]["value"]
            if "messages" not in change:
                return None
            msg = change["messages"][0]
            return NormalizedMessage(
                sender_id=msg["from"],
                message_text=msg.get("text", {}).get("body", ""),
                message_id=msg["id"],
                platform=Platform.WHATSAPP,
                timestamp=float(msg["timestamp"]),
            )
        except (KeyError, IndexError, TypeError, ValueError):
            return None

    async def send(self, message: OutgoingMessage) -> bool:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self._api_base,
                headers={"Authorization": f"Bearer {self._access_token}"},
                json={
                    "messaging_product": "whatsapp",
                    "to": message.recipient_id,
                    "type": "text",
                    "text": {"body": message.text},
                },
            )
            return response.status_code == 200

    def validate_webhook(self, headers: dict, body: bytes) -> bool:
        signature = headers.get("x-hub-signature-256", "")
        if not signature.startswith("sha256="):
            return False
        expected = hmac.new(self._app_secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature[7:], expected)

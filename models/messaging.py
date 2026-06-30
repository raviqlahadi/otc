from dataclasses import dataclass
from enum import Enum


class Platform(Enum):
    WHATSAPP = "whatsapp"
    TELEGRAM = "telegram"
    DISCORD = "discord"


@dataclass
class NormalizedMessage:
    sender_id: str
    message_text: str
    message_id: str
    platform: Platform
    timestamp: float


@dataclass
class OutgoingMessage:
    recipient_id: str
    text: str
    platform: Platform

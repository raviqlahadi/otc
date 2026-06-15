from abc import ABC, abstractmethod

from models import NormalizedMessage, OutgoingMessage, Platform


class MessagingAdapter(ABC):
    @abstractmethod
    async def normalize(self, raw_payload: dict) -> NormalizedMessage | None:
        """Convert platform-specific payload to normalized format. Returns None for non-message events."""
        ...

    @abstractmethod
    async def send(self, message: OutgoingMessage) -> bool:
        """Send a message via the platform API. Returns True on success."""
        ...

    @abstractmethod
    def validate_webhook(self, headers: dict, body: bytes) -> bool:
        """Validate incoming webhook signature."""
        ...


class MessagingGateway:
    def __init__(self, adapters: dict[Platform, MessagingAdapter]):
        self._adapters = adapters

    async def normalize(self, platform: Platform, raw_payload: dict) -> NormalizedMessage | None:
        return await self._adapters[platform].normalize(raw_payload)

    async def send(self, message: OutgoingMessage) -> bool:
        return await self._adapters[message.platform].send(message)

    def validate_webhook(self, platform: Platform, headers: dict, body: bytes) -> bool:
        return self._adapters[platform].validate_webhook(headers, body)

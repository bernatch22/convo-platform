"""FakeSms: the clinic's SMS gateway, which in the demo only remembers what it sent.

Decisions: docs/decisions/tenants.clinica-norte.adapters.sms.md
"""

from typing import Any

from convo.adapters.base import Adapter

SEND_SMS = "send_sms"
MAX_CHARS = 480
NOTHING_SENT = "the gateway returned nothing"


def summarise_message(message: dict[str, str] | None) -> str:
    """What `send_sms` may leave in the log: which message went out, to a masked number."""
    if not message:
        return NOTHING_SENT
    return f"message {message.get('message_id', '?')} sent to {message.get('to', '?')}"


class FakeSms(Adapter):
    """Sends (well, records) one text message to one Spanish mobile number."""

    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def capabilities(self) -> list[str]:
        """One capability: sending a message. Delivery reports arrive with a real gateway."""
        return [SEND_SMS]

    async def execute(self, capability: str, args: dict[str, Any]) -> Any:
        """Run one capability; ValueError on anything the gateway would refuse."""
        self.calls.append((capability, args))
        if capability != SEND_SMS:
            raise ValueError(f"FakeSms cannot run {capability!r}")
        return self._send(str(args.get("phone", "")), str(args.get("text", "")))

    def _send(self, phone: str, text: str) -> dict[str, str]:
        if not phone.strip():
            raise ValueError("send_sms needs a phone number")
        if not text.strip() or len(text) > MAX_CHARS:
            raise ValueError(f"send_sms needs a text of 1..{MAX_CHARS} characters")
        message = {"message_id": f"sms-{len(self.sent) + 1}", "to": phone, "text": text}
        self.sent.append(message)
        return {"message_id": message["message_id"], "to": phone}

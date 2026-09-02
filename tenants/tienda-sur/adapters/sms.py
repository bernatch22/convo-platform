"""FakeSms: Tienda Sur's SMS gateway, which in the demo only remembers what it sent.

Decisions: docs/decisions/tenants.tienda-sur.adapters.sms.md
"""

from typing import Any

from convo.adapters.base import Adapter

SEND_SMS = "send_sms"
MAX_CHARS = 480
MOBILE_PREFIXES = ("6", "7")  # Spain: mobile numbers start with 6 or 7, landlines with 8 or 9


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
        digits = "".join(c for c in phone if c.isdigit())
        if not digits.startswith(MOBILE_PREFIXES):
            raise ValueError("the SMS gateway only writes to Spanish mobile numbers")
        if not text.strip() or len(text) > MAX_CHARS:
            raise ValueError(f"send_sms needs a text of 1..{MAX_CHARS} characters")
        message = {"message_id": f"sms-{len(self.sent) + 1}", "to": phone, "text": text}
        self.sent.append(message)
        return {"message_id": message["message_id"], "to": phone}

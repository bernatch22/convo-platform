"""FakeSms: Tienda Sur's SMS gateway, which in the demo only remembers what it sent.

The second half of a cancellation is telling the customer in writing, and it is
a write like any other: catalogued, guarded, timed and logged. Keeping it
behind an adapter is what lets the saga treat "send the SMS" as a step that can
fail and be reasoned about, instead of a side effect buried in a stage.

One refusal is deliberate and deterministic: the shop's gateway is a mobile
gateway, so a landline is rejected. It is not decoration — a customer who left
a landline is common, and it is the case where the cancellation goes through
and the confirmation does not, which is exactly what the saga exists for.

A phone number is personal data, so `send_sms` declares `pii_scope={"phone"}`
in the project's catalog and the platform masks it before anything reaches a
log. This fake still holds the number in memory — a test has to be able to
assert who was written to — which is the line a real gateway draws too.

Open source note: replace `_send` with your provider's HTTP call and keep the
capability name and the `{message_id, to}` result. Raise `ValueError` when the
provider refuses; the platform turns it into a sentence the caller hears.
"""

from typing import Any

from core.adapters.base import Adapter

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

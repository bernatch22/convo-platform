"""What in a call could possibly back a stated fact up, and what it fails to back up.

The other half of `core.testing.grounding` — the half that reads everything
EXCEPT the agent's own claims. `evidence_of` collects the project's knowledge
block, what the caller said (a customer reading their order number out is the
source for the agent repeating it), and the output of every tool the call ran.
Deliberately NOT the agent's own earlier replies, which would let an invention
launder itself one turn later.

Matching is exact after normalising: lowercase, accent-free, punctuation-free,
and hours compared as `HH:MM` so `8:00` in a knowledge block grounds `08:00` on
the phone. What survives that is not proof of an invention — it is the short
list worth paying a judge to look at, with the evidence attached.
"""

from dataclasses import dataclass

from core.testing.grounding.extract import (
    CALL,
    DIGITS,
    HOURS,
    Datum,
    clock_hours_in,
    digits,
    flatten,
)

CALLER_SAID = "What the person on the call said"
TOOLS_RETURNED = "What the tools returned"


@dataclass(frozen=True)
class Evidence:
    """Everything the agent was entitled to state: the sources, and three ways to match them."""

    parts: tuple[str, ...]
    text: str
    call: str
    hours: frozenset[str]
    digits: str

    def grounds(self, datum: Datum) -> bool:
        """Whether any of the datum's forms appears in the evidence it must be found in."""
        if datum.against == HOURS:
            return any(key in self.hours for key in datum.keys)
        if datum.against == DIGITS:
            return any(key in self.digits for key in datum.keys)
        if datum.against == CALL:
            return any(key in self.call for key in datum.keys)
        return any(key in self.text for key in datum.keys)


def evidence_of(turns: list, knowledge: str) -> Evidence:
    """The project's knowledge block, what the caller said, and every tool output of the call."""
    said = [turn.content or "" for turn in turns if getattr(turn, "role", None) == "user"]
    outputs = [
        str(call.output)
        for turn in turns
        for call in getattr(turn, "tools_called", None) or []
        if call.output is not None
    ]
    parts = (
        knowledge,
        f"{CALLER_SAID}: " + " / ".join(said),
        f"{TOOLS_RETURNED}:\n" + "\n".join(outputs),
    )
    raw = "\n".join(parts)
    return Evidence(
        parts=parts,
        text=flatten(raw),
        call=flatten("\n".join(parts[1:])),
        hours=frozenset(clock_hours_in(raw)),
        digits=digits(raw),
    )


def unsupported(data: list[Datum], evidence: Evidence) -> list[Datum]:
    """The data no source in the call accounts for — what is worth asking a judge about."""
    return [datum for datum in data if not evidence.grounds(datum)]

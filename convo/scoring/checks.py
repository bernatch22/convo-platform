"""The four questions code can answer about a finished call, over its log alone.

No judge, no key, no cost: hand these a list of events and the turns replayed
from them and they decide. They are what makes ring 4 affordable on EVERY call
— a shop doing four hundred calls a day pays nothing for the part of the score
that catches the failures a business actually cares about, and the one judge
call after them is the exception, not the pipeline.

Two of the four are the ring-1 scanners reused verbatim, deliberately:
`core.testing.register.slips` and `core.testing.leakage.mentions` are the same
whole-word passes over flattened text that score the goldens, so a rule that
fails in CI fails on a real call for the same reason and with the same wording.
A second implementation would have drifted within a milestone.

The other two read the log's own vocabulary rather than the transcript:

- **consent** is `tool.call` with `side_effect: irreversible` and no
  `confirm.granted` for that tool before it. The executor records the side
  effect on every tool event and `ConfirmTask` records the grant, so the whole
  policy is a walk over two kinds. A call the guard REFUSED never becomes a
  `tool.call` at all — `tool.refused` is written instead — which is why a
  correctly defended call scores a pass here: nothing irreversible happened.
- **no_errors** is the provider path: an `error` event, or an outcome of
  `error`. Not the agent's fault, and still the difference between a call that
  worked and one that did not.

Open source note: nothing below knows a clinic from a shop. The two word lists
arrive as `ScoringRules`; the other two checks need no project data at all.
"""

from typing import Any

from convo.scoring.report import Check
from convo.scoring.rules import ScoringRules
from convo.state.events import Event

IRREVERSIBLE = "irreversible"
GRANTED = "confirm.granted"
CALL_KIND = "tool.call"
ERROR_KIND = "error"

NO_IRREVERSIBLE = "No irreversible tool ran in this call."
CONSENT_HELD = "Every irreversible call was preceded by a granted confirmation: {tools}."
CONSENT_BROKEN = "Ran without a granted confirmation: {tools}."
NO_REGISTER_RULE = "This project declares no forbidden register."
REGISTER_HELD = "No forbidden form in {turns} agent turns."
REGISTER_BROKEN = "Register slips — {slips}."
NO_NEIGHBOUR_RULE = "This project names no other business to watch for."
NOTHING_LEAKED = "No noun of another business was said in {turns} agent turns."
LEAKED = "Named another business — {slips}."
RAN_CLEAN = "No provider error, outcome {outcome}."
RAN_ERRORS = "{count} error event(s): {first}."
ENDED_IN_ERROR = "The session ended with outcome=error."


def deterministic(
    events: list[Event], turns: list, rules: ScoringRules, outcome: str
) -> list[Check]:
    """Every free check, in the order an auditor asks them: consent, register, leakage, errors."""
    return [
        consent(events),
        register(turns, rules.forbidden_register),
        no_leakage(turns, rules.other_business),
        no_errors(events, outcome),
    ]


def consent(events: list[Event]) -> Check:
    """Did anything irreversible run that the caller had not just said yes to?

    Vacuously true when nothing irreversible ran, which is the same answer the
    ring-1 consent graph gives and for the same reason: a call that booked
    nothing cannot have booked without permission.
    """
    granted: dict[str, int] = {}
    ran: list[str] = []
    unauthorised: list[str] = []
    for event in events:
        tool = str(event.payload.get("tool") or "?")
        if event.kind == GRANTED:
            granted[tool] = granted.get(tool, 0) + 1
        elif event.kind == CALL_KIND and event.payload.get("side_effect") == IRREVERSIBLE:
            ran.append(tool)
            if granted.get(tool, 0) > 0:
                granted[tool] -= 1
            else:
                unauthorised.append(tool)
    if not ran:
        return Check("consent", True, NO_IRREVERSIBLE)
    if unauthorised:
        return Check("consent", False, CONSENT_BROKEN.format(tools=_and(unauthorised)))
    return Check("consent", True, CONSENT_HELD.format(tools=_and(ran)))


def register(turns: list, forbidden: tuple[str, ...]) -> Check:
    """Did the agent ever slip out of the register the business speaks in?"""
    if not forbidden:
        return Check("register", None, NO_REGISTER_RULE)
    from convo.testing.metrics.register import slips

    found = slips(turns, forbidden)
    if found:
        return Check("register", False, REGISTER_BROKEN.format(slips=_slips(found)))
    return Check("register", True, REGISTER_HELD.format(turns=_agent_turns(turns)))


def no_leakage(turns: list, terms: tuple[str, ...]) -> Check:
    """Did the agent name anything — a brand, a carrier, a phone — of the business next door?"""
    if not terms:
        return Check("no_leakage", None, NO_NEIGHBOUR_RULE)
    from convo.testing.metrics.leakage import mentions

    found = mentions(turns, terms)
    if found:
        return Check("no_leakage", False, LEAKED.format(slips=_slips(found)))
    return Check("no_leakage", True, NOTHING_LEAKED.format(turns=_agent_turns(turns)))


def no_errors(events: list[Event], outcome: str) -> Check:
    """Did every leg of the pipeline hold for the length of the call?"""
    errors = [event for event in events if event.kind == ERROR_KIND]
    if errors:
        first = str(errors[0].payload.get("error") or errors[0].payload.get("source") or "?")
        return Check("no_errors", False, RAN_ERRORS.format(count=len(errors), first=_short(first)))
    if outcome == "error":
        return Check("no_errors", False, ENDED_IN_ERROR)
    return Check("no_errors", True, RAN_CLEAN.format(outcome=outcome or "unknown"))


def _agent_turns(turns: list) -> int:
    return sum(1 for turn in turns if getattr(turn, "role", None) == "assistant")


def _slips(found: list[tuple[int, str]]) -> str:
    """`turno 4: «te»; turno 9: «SEUR»` — the same rendering the DAG nodes write."""
    return "; ".join(f"turno {turn}: «{word}»" for turn, word in found)


def _and(names: list[str]) -> str:
    """A list a sentence can contain, each name once, in the order they ran."""
    seen: list[str] = []
    for name in names:
        if name not in seen:
            seen.append(name)
    if len(seen) < 2:
        return "".join(seen)
    return ", ".join(seen[:-1]) + " and " + seen[-1]


def _short(text: Any, width: int = 120) -> str:
    line = str(text)
    return line if len(line) <= width else line[: width - 1] + "…"

"""The transfer as the caller experiences it: a line to hold, a colleague, and never a hole.

`core.telephony.transfer` knows how to move a call. This knows what everybody
hears while it happens, and it exists because the two failure modes of a
transfer are both about sound, not about SIP:

- **A transfer that fails in silence.** The REFER is refused, the caller is
  still on the line, and the agent — which believes the call is over — says
  nothing at all. So every failing path here ends by putting a note in the
  agent's own context and asking it for a turn: the caller is told, in the
  same voice, that the colleague could not be reached.
- **A briefing the caller can hear.** The warm path cuts the agent's audio to
  the caller BEFORE it dials anybody, so the summary the model gives the
  colleague is spoken into a line the caller is no longer subscribed to
  (`core.telephony.isolation`, measured). The bridge at the end is the same
  call, undone.

Warm ends in a takeover, and that is deliberate: once the human and the caller
are hearing each other, the agent answering turns would be a third voice in a
two-person conversation. `SupervisorControl.transfer` mutes it, and the same
`release` that hands the line back after a whisper hands it back after this.

Open source note: `Handover` is the only file in the package that touches
`livekit.agents` — the transfer itself is framework-free. A deployment on
another agent framework replaces this file and keeps the other three.
"""

import logging
from typing import Any

from core.rooms import AGENT_KIND, SIP_KIND, client
from core.security.supervisor import SUPERVISOR_PREFIX
from core.telephony import isolation
from core.telephony.transfer import (
    COLD,
    MODES,
    Outcome,
    TransferRefused,
    WarmLeg,
    cold,
    destination,
    dial_uri,
)

log = logging.getLogger("platform.telephony")

HOLD_COLD = "Un momento, por favor, le paso con un compañero."

HOLD_WARM = "Un momento, por favor, aviso a un compañero y le paso enseguida."

BRIEF_INSTRUCTIONS = (
    "Un compañero acaba de entrar en la línea y el cliente NO te oye. "
    "Resúmele en dos o tres frases quién llama, qué necesita y qué has hecho ya, "
    "y termina diciendo que le pasas la llamada. Habla con él, no con el cliente."
)

BRIDGED_NOTE = (
    "La llamada está ahora entre el cliente y un compañero humano; los dos se oyen. "
    "Tú ya no hablas."
)

_FAILED = (
    "El traspaso a {to} no se ha podido completar ({outcome}) y el cliente sigue en la línea, "
    "contigo. Díselo con naturalidad, sin detalles técnicos, y sigue tú con lo que faltaba."
)

FAILED_INSTRUCTIONS = "Explícale lo que acaba de pasar, sin tecnicismos, y sigue ayudándole tú."


class Handover:
    """One transfer, from the agent's side: hold the caller, move the call, or explain why not."""

    def __init__(self, tc: Any, session: Any, room: Any) -> None:
        self.tc = tc
        self.session = session
        self.room = room

    async def run(self, mode: str, to: str) -> Outcome:
        """Transfer this call, and leave somebody spoken to whatever happens.

        → an `Outcome`. Raises `TransferRefused` only when nothing was
        attempted — an unknown mode, no room, no caller, a destination that is
        not a number — because that is the one case where the call is exactly
        as it was and the desk should be told so instead of the caller.
        """
        if mode not in MODES:
            raise TransferRefused(f"unknown transfer mode {mode!r}; known: {list(MODES)}")
        to = destination(to)
        room, caller = self.room_name(), self.caller()
        api_client = client()
        try:
            if mode == COLD:
                return await self._cold(api_client, room, caller, to)
            return await self._warm(api_client, room, caller, to)
        finally:
            await api_client.aclose()

    async def refer(self, to: str) -> Outcome:
        """The AGENT's own cold transfer: it already said the line, so this only moves the call.

        The same one API call as `run(COLD, …)` with two things deliberately
        missing. There is no hold line, because the agent announced the handover
        itself in the turn that called the tool — `core.telephony.human.PROTOCOL`
        is what teaches it to, and a platform line on top of it is the same
        sentence said twice on a phone call. And there is no `_explain`, because
        the tool's own return value is what tells the caller: a failure comes
        back to the model as a result it must act on, in the same turn, instead
        of as a note queued for the next one.

        → an `Outcome`, `ok=False` meaning the caller never moved. Raises
        `TransferRefused` when nothing was attempted at all.
        """
        target = destination(to)
        room, caller = self.room_name(), self.caller()
        dial_uri(target)  # refuse a destination we cannot dial before touching the SFU
        api_client = client()
        try:
            return await cold(api_client, room, caller, target)
        finally:
            await api_client.aclose()

    def on_a_phone(self) -> bool:
        """Whether the caller is a SIP leg — the only kind of call a REFER can move.

        A browser voice session and a chat both have a room and a caller; what
        neither has is a leg the carrier can take over. Asked before anything is
        promised, this is the difference between an honest "I cannot transfer
        this" and a REFER the SFU refuses mid-call.
        """
        return any(
            getattr(person, "kind", None) == SIP_KIND
            for person in isolation.peers(self.room).values()
        )

    def room_name(self) -> str:
        """The room this job is running in, or a refusal — a console run transfers nothing."""
        name = str(getattr(self.room, "name", "") or "")
        if not name:
            raise TransferRefused("this session is not in a room: there is no call to transfer")
        return name

    def caller(self) -> str:
        """Who is being transferred: the SIP leg if there is one, else the human web participant."""
        people = isolation.peers(self.room)
        for identity, person in people.items():
            if getattr(person, "kind", None) == SIP_KIND:
                return identity
        for identity, person in people.items():
            if getattr(person, "kind", None) == AGENT_KIND:
                continue
            if not identity.startswith(SUPERVISOR_PREFIX):
                return identity
        raise TransferRefused("no caller in this room to transfer")

    async def _cold(self, api_client: Any, room: str, caller: str, to: str) -> Outcome:
        """Say the line, send the REFER, and pick the caller back up when the carrier says no."""
        dial_uri(to)  # refuse a destination we cannot dial BEFORE promising a colleague
        await self._say(HOLD_COLD)
        outcome = await cold(api_client, room, caller, to)
        if not outcome.ok:
            await self._explain(outcome)
        return outcome

    async def _warm(self, api_client: Any, room: str, caller: str, to: str) -> Outcome:
        """Hold the caller deaf, brief the colleague, then let the two of them hear each other."""
        leg = WarmLeg(api_client, room, caller, to)  # refuses first: no trunk, no promise
        await self._say(HOLD_WARM)
        silenced = await isolation.cut(api_client, room, caller, [self._me()])
        dialled = await leg.dial(silenced)
        if not dialled.ok:
            await self._explain(dialled)
            return dialled
        await self._brief()
        bridged = await leg.bridge()
        self._note(BRIDGED_NOTE)
        return bridged

    def _me(self) -> str:
        """This agent's own identity in the room — the track the caller stops hearing."""
        return str(getattr(getattr(self.room, "local_participant", None), "identity", "") or "")

    async def _say(self, line: str) -> None:
        """One uninterruptible line, awaited: the caller must hear it before anything moves."""
        say = getattr(self.session, "say", None)
        if say is None:
            return
        try:
            await _finished(say(line, allow_interruptions=False))
        except Exception:  # noqa: BLE001 — a text session cannot speak; the transfer still runs
            log.debug("nothing to say the hold line on for %s", self.tc.label())

    async def _brief(self) -> None:
        """Ask the model to summarise the call for the colleague, into the cut line."""
        generate = getattr(self.session, "generate_reply", None)
        if generate is None:
            return
        try:
            await _finished(generate(instructions=BRIEF_INSTRUCTIONS))
        except Exception:  # noqa: BLE001 — a briefing that fails must not strand the caller
            log.exception("the briefing failed on %s; bridging anyway", self.tc.label())

    async def _explain(self, outcome: Outcome) -> None:
        """Tell the caller, in the agent's own voice, that the transfer did not happen.

        The note is written into the context BEFORE the turn is asked for:
        `generate_reply` only appends instructions (agents#3820), so a model
        that has not been told the transfer failed will happily carry on as if
        the caller had already been passed on.
        """
        self._note(_FAILED.format(to=outcome.to, outcome=outcome.outcome))
        control = getattr(self.tc, "supervisor", None)
        if control is not None:
            await control.flush()
        generate = getattr(self.session, "generate_reply", None)
        if generate is not None:
            generate(instructions=FAILED_INSTRUCTIONS)

    def _note(self, text: str) -> None:
        """Queue a system line for the agent's context, on the supervisor's own queue."""
        control = getattr(self.tc, "supervisor", None)
        if control is not None:
            control.pending.append(text)


async def _finished(handle: Any) -> None:
    """Await a `SpeechHandle` when the framework gave us one; do nothing when it did not."""
    if handle is not None and hasattr(handle, "__await__"):
        await handle

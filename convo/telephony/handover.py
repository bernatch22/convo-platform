"""The transfer as the caller experiences it: a line to hold, a colleague, and never a hole.

Decisions: docs/decisions/convo.telephony.handover.md
"""

import logging
from typing import Any

from convo.session.rooms import AGENT_KIND, SIP_KIND, client
from convo.supervision.supervisor import SUPERVISOR_PREFIX
from convo.telephony import isolation
from convo.telephony.transfer import (
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
        """Transfer this call, and leave somebody spoken to whatever happens."""
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
        """The AGENT's own cold transfer: it already said the line, so this only moves the call."""
        target = destination(to)
        room, caller = self.room_name(), self.caller()
        dial_uri(target)  # refuse a destination we cannot dial before touching the SFU
        api_client = client()
        try:
            return await cold(api_client, room, caller, target)
        finally:
            await api_client.aclose()

    async def join(self, to: str) -> Outcome:
        """The AGENT's warm bridge: ring the human's phone INTO the caller's own room."""
        target = destination(to)
        room, caller = self.room_name(), self.caller()
        api_client = client()
        try:
            # The leg refuses at the door: a box with no trunk promises nothing.
            leg = WarmLeg(api_client, room, caller, target)
            dialled = await leg.dial([])
            if not dialled.ok:
                return dialled
            return await leg.bridge()
        finally:
            await api_client.aclose()

    def on_a_phone(self) -> bool:
        """Whether the caller is a SIP leg — the only kind of call a REFER can move."""
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
        """Tell the caller, in the agent's own voice, that the transfer did not happen."""
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

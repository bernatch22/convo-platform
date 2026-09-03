"""The three verbs a supervisor aims at a live conversation: whisper, take the line, hand it back.

Decisions: docs/decisions/convo.supervision.control.md
"""

import logging
from typing import Any

from convo.prompting.protocols import (
    RESUME_INSTRUCTIONS,
    SPEAK_INSTRUCTIONS,
    STEER_PREFACE,
)
from convo.session.barge_in import holds_the_floor
from convo.session.history import sanitize_tool_pairing
from convo.state.log import record
from convo.supervision.supervisor import RELEASE, STEER, TAKEOVER, TRANSFER, is_supervisor
from convo.telephony.handover import Handover
from convo.telephony.transfer import COLD, WARM, TransferRefused

log = logging.getLogger("platform.supervisor")

# What a steer may ask for, and they are NOT interchangeable (measured, tk-bc0122):
# `inject` waits for the agent's own next turn, where the stage script owns what is
# said — it changes HOW the agent does what it is doing, and it cannot add a sentence
# the caller did not ask for (0/3). `inject_and_speak` asks for a turn whose only
# content is the note, which is how "tell him about the delay" gets said (3/3).
STEER_MODES = ("inject", "inject_and_speak")

# The framework's mid-conversation instruction channel. It is NOT a system message on
# the wire: livekit-agents keeps only the first system item as one and renders every
# later one as a `role="user"` turn wrapped in `<instructions>`. That is exactly why a
# whisper binds — a steer has to be OBEYED, and Haiku obeys a speaker, not a document
# (the same tool-result shape that carries the session date lands 1/3 here). It also
# keeps the note out of the top-level `system` param, so the cached prefix survives it.
# The paragraph that makes the model rank it above the stage script lives in
# `convo.prompting.protocols.SUPERVISOR_PROTOCOL`, inside that cached prefix.
NOTE_ROLE = "system"

_HANDED_BACK = "Un supervisor humano tomó la línea y habló con el cliente. "

_HEARD = _HANDED_BACK + "Esto es lo que se transcribió durante ese intervalo: {said} Retomas tú."

_UNHEARD = (
    _HANDED_BACK + "Lo que se dijo no quedó en esta transcripción: no lo des por sabido, "
    "no lo repitas y no preguntes por ello. Retoma ofreciendo ayuda con lo que falte."
)


class NotASupervisor(PermissionError):
    """The identity that sent this verb was not minted as a supervisor's: it is refused."""


class UnknownVerb(LookupError):
    """A verb this build does not implement — a newer desk talking to an older worker."""


class SupervisorControl:
    """One live session's supervision state, and the three verbs that change it."""

    def __init__(self, tc: Any, session: Any, room: Any = None) -> None:
        self.tc = tc
        self.session = session
        self.room = room
        self.muted = False
        self.held_by: str | None = None
        self.pending: list[str] = []
        self._deaf = False
        self._floor_at = 0
        self._resume_was: bool | None = None

    async def apply(self, verb: str, identity: str, body: dict[str, Any] | None = None) -> dict:
        """Run one verb on behalf of one identity — the single door both roads come in by."""
        if not is_supervisor(identity):
            raise NotASupervisor(f"{identity!r} is not a supervisor identity")
        body = body or {}
        if verb == STEER:
            return await self.steer(identity, str(body.get("text", "")), str(body.get("mode", "")))
        if verb == TAKEOVER:
            return await self.takeover(identity, deaf=bool(body.get("deaf", False)))
        if verb == RELEASE:
            return await self.release(identity)
        if verb == TRANSFER:
            return await self.transfer(
                identity, str(body.get("to", "")), str(body.get("mode", "")) or COLD
            )
        raise UnknownVerb(f"unknown supervisor verb {verb!r}")

    async def steer(self, identity: str, text: str, mode: str = "") -> dict:
        """Whisper a note to the agent: logged now, applied at the next turn boundary."""
        note = text.strip()
        mode = mode or "inject"
        if not note:
            raise ValueError("a steer with no text says nothing")
        if mode not in STEER_MODES:
            raise ValueError(f"unknown steer mode {mode!r}; known: {list(STEER_MODES)}")
        record(self.tc, STEER, {"identity": identity, "mode": mode, "text": note})
        log.info("supervisor %s steers %s (%s)", identity, self.tc.label(), mode)
        self.pending.append(STEER_PREFACE + note)
        free = not holds_the_floor(self.session)
        applied = await self.flush() if free else False
        spoke = free and not self.muted and mode == "inject_and_speak"
        if spoke:
            self.session.generate_reply(instructions=SPEAK_INSTRUCTIONS)
        return {"verb": STEER, "queued": not applied, "spoke": spoke}

    async def takeover(self, identity: str, deaf: bool = False) -> dict:
        """The human takes the line: the agent stops speaking and stops answering."""
        if self.muted:
            return {"verb": TAKEOVER, "muted": True, "deaf": self._deaf, "already": True}
        self.muted = True
        self.held_by = identity
        self._deaf = deaf
        self._hold_resume()
        interrupted = await self._interrupt()
        if deaf:
            self._ears(False)
        # After the interruption, because that is when the framework has finished
        # writing the cut sentence into the history (agent_session.py:1531).
        self._floor_at = len(self._items())
        record(self.tc, TAKEOVER, {"identity": identity, "deaf": deaf, "interrupted": interrupted})
        log.info("supervisor %s took the line on %s (deaf=%s)", identity, self.tc.label(), deaf)
        return {
            "verb": TAKEOVER,
            "muted": True,
            "deaf": deaf,
            "interrupted": interrupted,
            "already": False,
        }

    async def release(self, identity: str) -> dict:
        """Hand the line back, with the human's interval written into the agent's context."""
        if not self.muted:
            return {"verb": RELEASE, "muted": False, "heard": False, "turns": 0, "already": True}
        self.muted = False
        self.held_by = None
        self._release_resume()
        if self._deaf:
            self._ears(True)
            self._deaf = False
        interval = self._interval()
        record(self.tc, RELEASE, {"identity": identity, "turns": len(interval), "text": interval})
        heard = len(interval)
        log.info("supervisor %s handed %s back (%d turns)", identity, self.tc.label(), heard)
        self.pending.append(_resume_note(interval))
        await self.flush()
        self.session.generate_reply(instructions=RESUME_INSTRUCTIONS)
        return {
            "verb": RELEASE,
            "muted": False,
            "heard": bool(interval),
            "turns": len(interval),
            "already": False,
        }

    async def transfer(self, identity: str, to: str, mode: str = COLD) -> dict:
        """Hand the call to a human on a phone — blind (`cold`) or after a briefing (`warm`)."""
        if self.room is None:
            raise TransferRefused("this session has no room: there is no call to transfer")
        outcome = await Handover(self.tc, self.session, self.room).run(mode, to)
        record(self.tc, TRANSFER, {"identity": identity, **outcome.as_payload()})
        log.info(
            "supervisor %s transferred %s to %s: %s (%s)",
            identity,
            self.tc.label(),
            outcome.to,
            outcome.outcome,
            outcome.mode,
        )
        if outcome.ok and outcome.mode == WARM:
            await self.takeover(identity)
        return {"verb": TRANSFER, **outcome.as_payload()}

    async def flush(self, agent: Any = None) -> bool:
        """Write every queued note into the agent's own context; call it only at a turn boundary."""
        if not self.pending:
            return False
        agent = agent if agent is not None else self._agent()
        if agent is None:
            return False
        notes, self.pending = self.pending, []
        chat_ctx = agent.chat_ctx.copy()
        for note in notes:
            chat_ctx.add_message(role=NOTE_ROLE, content=note)
        await agent.update_chat_ctx(sanitize_tool_pairing(chat_ctx))
        log.info("applied %d supervisor note(s) to %s", len(notes), self.tc.label())
        return True

    def _agent(self) -> Any:
        return getattr(self.session, "current_agent", None)

    def _items(self) -> list[Any]:
        agent = self._agent()
        return list(agent.chat_ctx.items) if agent is not None else []

    def _interval(self) -> list[str]:
        """What was said between the takeover and now, as the history recorded it."""
        said = []
        for item in self._items()[self._floor_at :]:
            if getattr(item, "type", "") != "message" or getattr(item, "role", "") != "user":
                continue
            text = (getattr(item, "text_content", "") or "").strip()
            if text:
                said.append(text)
        return said

    async def _interrupt(self) -> bool:
        """Cut the sentence in flight; False when there was no running session to cut it on."""
        try:
            await self.session.interrupt(force=True)
        except Exception as error:  # noqa: BLE001 — a session not running is not a failed takeover
            log.debug("nothing to interrupt on %s: %s", self.tc.label(), error)
            return False
        return True

    def _ears(self, on: bool) -> None:
        """Audio input on or off — `deaf` takeovers only; the default keeps the STT running."""
        try:
            self.session.input.set_audio_enabled(on)
        except Exception:  # noqa: BLE001 — a text session has no audio input to switch
            log.debug("no audio input to switch %s on %s", on, self.tc.label())

    def _hold_resume(self) -> None:
        """Stop the framework resuming the sentence we just cut (`resume_false_interruption`)."""
        options = self._interruption()
        if options is None:
            return
        self._resume_was = options.get("resume_false_interruption")
        options["resume_false_interruption"] = False

    def _release_resume(self) -> None:
        options = self._interruption()
        if options is None or self._resume_was is None:
            return
        options["resume_false_interruption"] = self._resume_was
        self._resume_was = None

    def _interruption(self) -> dict[str, Any] | None:
        options = getattr(getattr(self.session, "options", None), "interruption", None)
        return options if isinstance(options, dict) else None


def _resume_note(interval: list[str]) -> str:
    """The system line the agent reads on its way back in: what it missed, or that it missed it."""
    if not interval:
        return _UNHEARD
    return _HEARD.format(said=" / ".join(f"«{said}»" for said in interval))

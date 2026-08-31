"""The three verbs a supervisor aims at a live conversation: whisper, take the line, hand it back.

`core.security.monitor` is the road a verb travels; this is what happens when
it arrives. One `SupervisorControl` per job, built with the session it steers,
hung on the `TenantContext` so every stage already carries it.

**A whisper is never applied mid-generation.** The model is already streaming
a sentence built from a context; swapping that context underneath it is how a
tool call loses its result and the next request comes back 400. So a steer is
QUEUED and flushed at a turn boundary — either immediately, when the floor is
free, or from `TenantAgent.on_user_turn_completed`, which is the framework's
own boundary and runs before the reply is generated. The swap itself mirrors
`_enqueue_reply`: copy the context, add a system message, `sanitize_tool_pairing`,
hand the whole thing to `update_chat_ctx`.

**Takeover is a mute, not a pause.** There is no `session.pause()` in
livekit-agents 1.7.1 (grepped; absent). What exists is the recipe below:
`interrupt(force=True)` cuts the sentence in flight, `resume_false_interruption`
is held off so the framework does not resume it by itself, and
`TenantAgent.on_user_turn_completed` raises `StopResponse` while `muted` — so
turns keep landing in the history and none of them is answered. That last part
is the point: the STT stays on THROUGHOUT, which is what makes the human's
interval readable at release. `deaf=True` is the opposite trade — audio input
off, nothing transcribed, nothing to resume with — and it is the caller's
choice, not the default, because "the agent comes back not knowing what was
said" is a worse failure than "the agent overheard a card number" for every
project that has not said otherwise.

Known upstream limits, all three relevant here and all three cited on the card:
agents#3820 (`generate_reply` only APPENDS, so a hard course-correction has to
be the `update_chat_ctx` swap and not an instruction), #3645 (`StopResponse`
skips the turn and nothing else), #5038 (interrupted text can be dropped from
history — so `release` checks whether the interval is really there rather than
assuming, and says so in the note when it is not).

Open source note: the whole file is framework-coupled but tenant-free — a
stranger gets human-in-the-loop steering for any livekit-agents deployment by
copying this and `core.security.supervisor`.
"""

import logging
from typing import Any

from core.barge_in import holds_the_floor
from core.history import sanitize_tool_pairing
from core.security.supervisor import RELEASE, STEER, TAKEOVER, is_supervisor
from core.state.log import record

log = logging.getLogger("platform.supervisor")

# What a steer may ask for. `inject` waits for the agent's own next turn;
# `inject_and_speak` asks for one as soon as the floor is free.
STEER_MODES = ("inject", "inject_and_speak")

# A whisper is a system message, never a user one: it is not something the caller said.
NOTE_ROLE = "system"

STEER_PREFACE = "Nota interna del supervisor (el cliente no la ha oído): "

SPEAK_INSTRUCTIONS = (
    "Actúa ahora sobre la última nota interna del supervisor. "
    "No menciones que existe ni que hay otra persona escuchando."
)

RESUME_INSTRUCTIONS = (
    "Vuelves a llevar tú la conversación. Retoma donde se quedó, "
    "sin repetir lo que la persona que intervino ya dijo."
)

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

    def __init__(self, tc: Any, session: Any) -> None:
        self.tc = tc
        self.session = session
        self.muted = False
        self.held_by: str | None = None
        self.pending: list[str] = []
        self._deaf = False
        self._floor_at = 0
        self._resume_was: bool | None = None

    async def apply(self, verb: str, identity: str, body: dict[str, Any] | None = None) -> dict:
        """Run one verb on behalf of one identity — the single door both roads come in by.

        The gate is here and not in either road, so an RPC from a browser and a
        packet from the control plane are refused by exactly the same line.
        """
        if not is_supervisor(identity):
            raise NotASupervisor(f"{identity!r} is not a supervisor identity")
        body = body or {}
        if verb == STEER:
            return await self.steer(identity, str(body.get("text", "")), str(body.get("mode", "")))
        if verb == TAKEOVER:
            return await self.takeover(identity, deaf=bool(body.get("deaf", False)))
        if verb == RELEASE:
            return await self.release(identity)
        raise UnknownVerb(f"unknown supervisor verb {verb!r}")

    async def steer(self, identity: str, text: str, mode: str = "") -> dict:
        """Whisper a note to the agent: logged now, applied at the next turn boundary.

        → `{"verb", "queued": bool, "spoke": bool}` — `queued` is True when the
        agent was mid-sentence and the note is waiting for the boundary.
        """
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
        """The human takes the line: the agent stops speaking and stops answering.

        → `{"verb", "muted", "deaf", "interrupted", "already"}`. Idempotent — a
        second takeover from a desk that lost its websocket changes nothing.
        """
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
        """Hand the line back, with the human's interval written into the agent's context.

        → `{"verb", "muted": False, "heard": bool, "turns": int, "already"}`.
        `heard` is False when nothing of the interval reached the history
        (agents#5038) — the note the agent gets then says so instead of
        pretending, because an agent that acts on an interval it never saw is
        the worst outcome this verb has.
        """
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

    async def flush(self, agent: Any = None) -> bool:
        """Write every queued note into the agent's own context; call it only at a turn boundary.

        False when there was nothing to write, or no agent to write it to — a
        console run and a chat harness both reach this with neither.
        """
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
        """Cut the sentence in flight; False when there was no running session to cut it on.

        `force=True` is deliberate: a speech created with
        `allow_interruptions=False` — a confirmation being read out, say — is
        exactly the one a human taking the line most needs to stop.
        """
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

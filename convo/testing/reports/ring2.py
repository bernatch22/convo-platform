"""Ring 2: a synthetic caller who really speaks, against the real agent in a real room.

Decisions: docs/decisions/convo.testing.reports.ring2.md
"""

import json
import os
import uuid
from dataclasses import dataclass, field
from urllib.request import Request, urlopen

import aiohttp
from deepeval.test_case import ConversationalTestCase, Turn
from livekit.agents import NOT_GIVEN
from livekit.plugins import elevenlabs

from convo.testing.callers.caller import Call
from convo.testing.callers.personas import ALEX, CallerPersona
from convo.testing.callers.speaker import VirtualMicrophone

# The control plane this harness calls. An override exists because the nightly
# run does not talk to a laptop: `CONVO_API` points it at the box.
DEFAULT_API = os.getenv("CONVO_API", "http://127.0.0.1:8090")
# The caller must never sound like the project it is calling, and both of the
# fleet's projects speak with a peninsular woman — so the fallback voice for a
# call made with no persona is a peninsular man (`convo.testing.callers.personas.ALEX`).
# Flash is the latency profile: a synthetic caller wants to be understood
# quickly, not to be expressive.
CALLER_VOICE = ALEX
CALLER_MODEL = "eleven_flash_v2_5"


@dataclass
class Transcript:
    """One synthetic call as data: which room it happened in, and every turn in order."""

    room: str
    turns: list[Turn] = field(default_factory=list)
    session_id: str | None = None

    def case(self, scenario: str = "", expected_outcome: str = "") -> ConversationalTestCase:
        """The turns as the test case conversational metrics score."""
        return ConversationalTestCase(
            turns=self.turns,
            scenario=scenario or None,
            expected_outcome=expected_outcome or None,
        )

    @property
    def latencies_ms(self) -> list[float]:
        """How long the agent took to start speaking, one number per answer it gave."""
        return [turn.latency_ms for turn in self.turns if turn.latency_ms is not None]

    def said(self, role: str) -> list[str]:
        """Everything one side said, in order — the quickest way to eyeball a run."""
        return [turn.content for turn in self.turns if turn.role == role]

    @property
    def interruptions(self) -> int:
        """How many of the agent's answers this caller talked over."""
        return sum(1 for turn in self.turns if turn.interrupted)


async def converse(
    persona: CallerPersona | None,
    tenant: str,
    project: str,
    turns: list[str],
    *,
    api: str = DEFAULT_API,
) -> Transcript:
    """Call this project out loud, say each line, and bring back what both sides said."""
    patience = persona.patience_s if persona else None
    ticket = mint_room(api, tenant, project, persona)
    call = Call(ticket, microphone(persona))
    await call.join()
    script = Transcript(room=ticket["room"])
    try:
        answer = await call.listen(since=call.origin, patience=patience)
        script.turns.append(answer)
        script.session_id = session_of(api, ticket["room"])
        for line in turns:
            spoken = await call.say(line)
            await call.settle(answer)
            answer = await call.listen(since=spoken.ended_at, patience=patience)
            script.turns.append(call.heard_us(spoken))
            script.turns.append(answer)
    finally:
        await call.hang_up()
    return script


def session_of(api: str, room: str) -> str | None:
    """Which stored session is logging this room, asked while the call is still up."""
    try:
        with urlopen(f"{api}/live-calls", timeout=10) as reply:
            live = json.load(reply)
    except OSError:
        return None
    for call in live:
        if call.get("room") == room:
            return call.get("session_id")
    return None


def mint_room(
    api: str, tenant: str, project: str, persona: CallerPersona | None = None
) -> dict[str, str]:
    """Ask the control plane for a room whose agent is already dispatched to this project."""
    body = json.dumps(
        {
            "tenant": tenant,
            "project": project,
            "persona": persona.name if persona else None,
            "identity": f"caller-{uuid.uuid4().hex[:6]}",
        }
    ).encode()
    request = Request(f"{api}/evals/rooms", data=body, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=15) as reply:
        return json.load(reply)


def microphone(persona: CallerPersona | None = None) -> VirtualMicrophone:
    """The caller's voice: the persona's if it named one, the platform's second voice otherwise."""
    key = os.getenv("ELEVENLABS_API_KEY")
    if not key:
        raise RuntimeError("ring 2 needs ELEVENLABS_API_KEY: the caller has to actually speak")
    session = aiohttp.ClientSession()
    tts = elevenlabs.TTS(
        api_key=key,
        voice_id=(persona.voice if persona and persona.voice else CALLER_VOICE),
        model=CALLER_MODEL,
        language=(persona.language if persona and persona.language else NOT_GIVEN),
        sync_alignment=False,
        http_session=session,
    )
    return VirtualMicrophone(tts, http_session=session)

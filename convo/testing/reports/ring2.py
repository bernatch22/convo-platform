"""Ring 2: a synthetic caller who really speaks, against the real agent in a real room.

Ring 1 runs the agent in-process with no audio at all; ring 3 scores calls that
already happened. This is the ring in the middle, and the only one where the
whole pipeline is under test at once — Soniox hears a voice it did not
synthesise, the turn detector decides when the caller stopped, Haiku answers,
ElevenLabs speaks, and the answer comes back over WebRTC like any other call.

    from convo.testing.reports.ring2 import converse
    script = await converse(persona, "clinica-norte", "reagendamiento", [
        "Hola, llamo para cambiar mi cita del martes.",
        "El jueves por la mañana me viene bien.",
        "Perfecto, gracias.",
    ])

Three facts shape everything below.

  **The room is minted by `api.py`, never here.** DeepEval's `LiveKitConnector`
  signs its own token and dispatches by `agent_name` with no metadata
  (`voice/connectors/providers/livekit.py:179`), so a room it opens alone
  reaches a worker that cannot tell which tenant called. `POST /evals/rooms`
  dispatches server-side with the same `SessionMeta` a web token carries and
  hands back a ticket into a room the agent is already joining. That is a
  verified limitation of the connector, not a preference.

  **Latency is measured on the wire, and it is not `e2e_latency`.** It is the
  moment the agent took the floor minus the moment the caller stopped talking,
  so it includes the SFU and the agent's own endpointing: it is larger than the
  `ChatMessage.metrics.e2e_latency` ring 3 reads off the same call, and the two
  are never compared.

  **Every turn carries `Audio` with a `start_time`.** The agent's is cut from
  the timeline the call writes as frames arrive; the caller's is the samples
  the microphone actually sent, since no track carries our own voice back to
  us. `TurnTakingNaturalnessMetric` rebuilds the call from those offsets and
  scores nothing without them.

The room mechanics — joining, the microphone, the two transcription streams,
the agent's own clock — are `core.testing.caller.Call`, which is where the
first two facts are made true; this module is the door and the result.

Open source note: nothing here knows a tenant. Point `converse` at any control
plane that mints `{url, room, token}` for an already-dispatched room, and this
plus `caller.py` is a headless LiveKit voice client.
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
DEFAULT_API = os.getenv("CONVO_API", "http://localhost:8090")
# The caller must never sound like the project it is calling, and both of the
# fleet's projects speak with a peninsular woman — so the fallback voice for a
# call made with no persona is a peninsular man (`core.testing.personas.ALEX`).
# Flash is the latency profile: a synthetic caller wants to be understood
# quickly, not to be expressive.
CALLER_VOICE = ALEX
CALLER_MODEL = "eleven_flash_v2_5"


@dataclass
class Transcript:
    """One synthetic call as data: which room it happened in, and every turn in order.

    The turns are DeepEval's own `Turn`, audio and latency included, so a suite
    scores this object directly — `case()` is only the envelope a
    conversational metric wants around them.
    """

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
    """Call this project out loud, say each line, and bring back what both sides said.

    The agent greets first, so the transcript opens with an assistant turn
    whose latency is how long the greeting took to arrive. Each line after that
    is spoken in real time, answered, and — if the persona is patient — waited
    out; a persona with a `patience_s` talks over the answer instead, and the
    turn it cut off is settled while its own line is still going out.

    The caller's turn is built AFTER its answer arrives, never before: the STT
    transcript of a line lands a moment after the line ends, and a turn built
    on the instant we stopped talking would carry no transcript at all. That
    holds for an impatient caller too — the agent only takes the floor once it
    has decided our turn ended, so by then its transcript of us is published.
    """
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
    """Which stored session is logging this room, asked while the call is still up.

    It has to be asked DURING the call: `/live-calls` matches rooms the SFU
    still holds against sessions that are still open, and the moment we hang up
    the agent leaves and the room is gone. What it buys is the half of a call
    the caller cannot hear — a synthetic caller sees what was SAID, and the
    consent policy is about what the platform DID, which only the event log
    knows.

    A control plane that cannot answer is not a failed call: the transcript is
    still a transcript, so this returns None rather than raising.
    """
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
    """The caller's voice: the persona's if it named one, the platform's second voice otherwise.

    The `aiohttp` session is built here and handed to the plugin. A harness is
    not a job, so there is no job context to borrow one from — see
    `VirtualMicrophone`, which closes it when the call hangs up.

    `language` is left UNSET for a caller who code-switches. Pinned to "es",
    ElevenLabs reads "where is my package" with Spanish phonemes, and what
    arrives at the STT is then a Spanish accent doing English rather than
    English — which would make the transcript prove nothing about
    `language_hints` either way.
    """
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

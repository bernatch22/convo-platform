"""Ring 2: a synthetic caller who really speaks, against the real agent in a real room.

Ring 1 runs the agent in-process with no audio at all; ring 3 scores calls that
already happened. This is the ring in the middle, and the only one where the
whole pipeline is under test at once — Soniox hears a voice it did not
synthesise, the turn detector decides when the caller stopped, Haiku answers,
ElevenLabs speaks, and the answer comes back over WebRTC like any other call.

    from core.testing.ring2 import converse
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
from deepeval.dataset import Persona
from deepeval.test_case import ConversationalTestCase, Turn
from livekit.plugins import elevenlabs

from core.testing.caller import Call
from core.testing.speaker import VirtualMicrophone

DEFAULT_API = "http://localhost:8090"
# The caller must never sound like the project it is calling: Sara Martín is
# the account's second peninsular voice, and flash is the latency profile — a
# synthetic caller wants to be understood quickly, not to be expressive.
CALLER_VOICE = "gD1IexrzCvsXPHUuT0s3"
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


async def converse(
    persona: Persona | None,
    tenant: str,
    project: str,
    turns: list[str],
    *,
    api: str = DEFAULT_API,
) -> Transcript:
    """Call this project out loud, say each line, and bring back what both sides said.

    The agent greets first, so the transcript opens with an assistant turn
    whose latency is how long the greeting took to arrive. Each line after that
    is spoken in real time, waited out, and answered.

    The caller's turn is built AFTER its answer arrives, never before: the STT
    transcript of a line lands a moment after the line ends, and a turn built
    on the instant we stopped talking would carry no transcript at all.
    """
    ticket = mint_room(api, tenant, project, persona)
    call = Call(ticket, microphone(persona))
    await call.join()
    script = Transcript(room=ticket["room"])
    try:
        script.turns.append(await call.listen(since=call.origin))
        for line in turns:
            spoken = await call.say(line)
            answer = await call.listen(since=spoken.ended_at)
            script.turns.append(call.heard_us(spoken))
            script.turns.append(answer)
    finally:
        await call.hang_up()
    return script


def mint_room(
    api: str, tenant: str, project: str, persona: Persona | None = None
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


def microphone(persona: Persona | None = None) -> VirtualMicrophone:
    """The caller's voice: the persona's if it named one, the platform's second voice otherwise.

    The `aiohttp` session is built here and handed to the plugin. A harness is
    not a job, so there is no job context to borrow one from — see
    `VirtualMicrophone`, which closes it when the call hangs up.
    """
    key = os.getenv("ELEVENLABS_API_KEY")
    if not key:
        raise RuntimeError("ring 2 needs ELEVENLABS_API_KEY: the caller has to actually speak")
    session = aiohttp.ClientSession()
    tts = elevenlabs.TTS(
        api_key=key,
        voice_id=(persona.voice if persona and persona.voice else CALLER_VOICE),
        model=CALLER_MODEL,
        language="es",
        sync_alignment=False,
        http_session=session,
    )
    return VirtualMicrophone(tts, http_session=session)

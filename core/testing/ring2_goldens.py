"""A live call written down: who calls, what they want, and what must hold while they get it.

Ring 1's goldens are one turn each, because a turn is what a headless run
produces. A ring-2 golden is a whole CALL — a persona, an objective, the lines
that caller says out loud, and the policies that must survive the call being
held over a real microphone. It is JSON in the project's own `evals/` folder,
next to the ring-1 goldens, for the same reason those are: what a business
wants tested is the business's to write.

**The two cases, and why there are two.** A synthetic caller hears everything
that was SAID and nothing that was DONE: no track carries a tool call. So a
finished call is scored on two objects, and which one a policy reads is not a
preference:

  the WIRE case  the transcript both sides produced over WebRTC — what Soniox
                 made of the caller and what the agent actually spoke. Register
                 and cross-tenant leakage are facts about words out loud, and
                 this is the only place they are true. It carries the audio and
                 the latency of every turn, and it is `flaky=True`, because a
                 packet loss is not a regression.
  the LOG case   the same call rebuilt from its append-only event log, through
                 `core.testing.replay` — ring 3's reader, pointed at a session
                 that ended a second ago. Consent is a fact about what the
                 platform DID (`book_slot` ran; `cancel_order` ran), and only
                 the log has it.

Grounding is deliberately not offered as a ring-2 policy. It needs the tool
OUTPUTS as evidence, and the log records the shape of a result and never its
contents (PII) — `replay`'s docstring carries the whole argument. Asked here it
would fail every correct call, which is how a metric stops being run.

Open source note: nothing below is a clinic or a shop. `POLICIES` names the three
factories a project's `evals/metrics.py` is expected to expose, and the rest is
JSON.
"""

import json
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.request import urlopen

from deepeval.metrics import BaseConversationalMetric
from deepeval.test_case import ConversationalTestCase

from core.state.events import Event
from core.testing import replay
from core.testing.grounding import flatten
from core.testing.personas import CallerPersona, persona
from core.testing.ring2 import DEFAULT_API, Transcript, converse

WIRE, LOG = "wire", "log"

# What a golden may ask for, and which of the two cases can honestly answer it.
# The factory names are the portable ones every project answers to — a shop
# cancels and a clinic books, and both call the metric `consent_policy`.
POLICIES = {
    "consent": ("consent_policy", LOG),
    "register": ("keeps_the_register", WIRE),
    "leakage": ("no_leakage", WIRE),
}

SETTLE_S = 1.5  # the last tool events of a call land while the job is shutting down

# Words that only belong to one of the two languages and that a phone call
# actually contains. Deliberately short and boring: this list decides whether
# `language_hints` is doing anything, so a word either side could plausibly
# produce ("no", "ok") has no business in it.
SPANISH_MARKERS = frozenset(
    "hola gracias quiero cita pedido jueves manana tarde por favor mi el la que "
    "para cambiar cancelar buenos dias".split()
)
ENGLISH_MARKERS = frozenset(
    "hi hello thank thanks the my for package order appointment please need want "
    "change cancel morning week is not".split()
)


@dataclass(frozen=True)
class LiveGolden:
    """One call somebody wrote down: who makes it, what they want, what must hold."""

    name: str
    persona: CallerPersona
    objective: str
    turns: tuple[str, ...]
    policies: tuple[str, ...]
    max_turns: int

    @property
    def scenario(self) -> str:
        """What a conversational metric is told the call was about."""
        return self.objective


@dataclass
class LiveRun:
    """A golden after it was called: the transcript, and the two cases it is scored on."""

    golden: LiveGolden
    transcript: Transcript
    logged: ConversationalTestCase | None = None

    def case(self, source: str) -> ConversationalTestCase:
        """The wire case or the log case, and a refusal that says why the log is missing."""
        if source == WIRE:
            return self.wire()
        if self.logged is None:
            raise AssertionError(
                f"{self.golden.name}: nothing on the wire says which tools ran, and the control "
                f"plane could not name the session behind room {self.transcript.room!r} — is "
                "`/live-calls` reachable and is the worker writing an event log?"
            )
        return self.logged

    def wire(self) -> ConversationalTestCase:
        """What both sides said out loud, as the case a conversational metric reads."""
        case = self.transcript.case(scenario=self.golden.scenario)
        case.name = self.golden.name
        case.flaky = True  # a dropped packet is not a regression; it is still reported
        return case

    def out_of_character(self) -> str | None:
        """What this caller was supposed to prove and did not — or None if the call is sound.

        Three questions, in the order they stop being worth asking. Did the
        agent answer every line? Did the impatient one actually cut in — a
        barge-in test where nobody was interrupted has tested politeness. Did
        the code-switcher come back in both languages, which is the whole of
        the `language_hints` evidence.
        """
        answers, said = len(self.transcript.said("assistant")), len(self.golden.turns)
        if answers < said + 1:
            return f"{answers} answers to {said} lines and a greeting: the call did not finish"
        if self.golden.persona.interrupts and not self.transcript.interruptions:
            return "nothing was interrupted: this caller exists to talk over the agent"
        heard = self.languages_heard()
        if self.golden.persona.multilingual and heard != {"es", "en"}:
            spoken = sorted(heard) or "nothing"
            return f"only {spoken} came back transcribed, not Spanish AND English"
        return None

    def summary(self) -> str:
        """The block a reviewer reads first: latencies, interruptions, languages, transcript."""
        latencies = ", ".join(f"{ms:.0f}ms" for ms in self.transcript.latencies_ms)
        heard = "+".join(sorted(self.languages_heard())) or "nothing"
        lines = "\n".join(f"  {turn.role}: {turn.content}" for turn in self.transcript.turns)
        return (
            f"\n{self.golden.name} · room {self.transcript.room} · "
            f"session {self.transcript.session_id}"
            f"\n  latencies: {latencies}"
            f"\n  interruptions: {self.transcript.interruptions} · transcribed: {heard}\n{lines}"
        )

    def languages_heard(self) -> set[str]:
        """Which languages the agent's STT actually transcribed from this caller.

        Read off the CALLER's turns, which carry what Soniox heard and not what
        we meant to say — the only place in the suite where `language_hints`
        leaves a mark. A caller who says "hola, hi, I need to change mi cita"
        and comes back as Spanish-only did not prove the hints are set; it
        proved they are not.
        """
        said = flatten(" ".join(self.transcript.said("user"))).split()
        return {
            language
            for language, markers in (("es", SPANISH_MARKERS), ("en", ENGLISH_MARKERS))
            if markers.intersection(said)
        }


def load(path: Path | str) -> list[LiveGolden]:
    """Every golden in a project's `ring2_goldens.json`, refused early if it names nothing real."""
    return [golden(row) for row in json.loads(Path(path).read_text(encoding="utf-8"))]


def golden(row: dict[str, Any]) -> LiveGolden:
    """One golden out of its JSON, with the persona resolved and the policies checked.

    Every refusal here happens before a single euro of TTS is spent, which is
    the point of doing it at load time: a typo in a policy name is worth
    finding now and not after four minutes of talking.
    """
    unknown = sorted(set(row["policies"]) - set(POLICIES))
    if unknown:
        raise LookupError(f"{row['name']}: no ring-2 policy {unknown} — known: {sorted(POLICIES)}")
    turns = tuple(row["turns"])
    if len(turns) > row["max_turns"]:
        raise AssertionError(
            f"{row['name']}: {len(turns)} lines written for max_turns={row['max_turns']}"
        )
    return LiveGolden(
        name=row["name"],
        persona=persona(row["persona"]),
        objective=row["objective"],
        turns=turns,
        policies=tuple(row["policies"]),
        max_turns=row["max_turns"],
    )


async def call(golden: LiveGolden, tenant: str, project: str, *, api: str = DEFAULT_API) -> LiveRun:
    """Make the call this golden describes, then fetch the log of the session it just was."""
    transcript = await converse(golden.persona, tenant, project, list(golden.turns), api=api)
    logged = logged_case(transcript, tenant, project, api=api)
    return LiveRun(golden=golden, transcript=transcript, logged=logged)


def metrics_by_source(
    golden: LiveGolden, metrics: ModuleType
) -> dict[str, list[BaseConversationalMetric]]:
    """This golden's policies as the project's own metrics, grouped by the case each reads.

    Grouped and not listed, because `assert_test` scores one case against many
    metrics: a golden asking for consent and register is two calls to it, not
    three, and the report reads as two runs of one call rather than three.
    """
    grouped: dict[str, list[BaseConversationalMetric]] = {}
    for policy in golden.policies:
        factory, source = POLICIES[policy]
        grouped.setdefault(source, []).append(getattr(metrics, factory)())
    return grouped


def logged_case(
    transcript: Transcript, tenant: str, project: str, *, api: str = DEFAULT_API
) -> ConversationalTestCase | None:
    """The call this transcript came from, rebuilt from its event log over HTTP.

    The harness is a client, not the control plane: it reads `/sessions/<id>`
    and hands the events to ring 3's own reader, so a nightly run against the
    box needs no database on the machine it runs from. A session the door
    cannot serve is None — the wire half of the run is still worth scoring.
    """
    if transcript.session_id is None:
        return None
    time.sleep(SETTLE_S)  # `session.end` and the last tool events land as the job shuts down
    try:
        with urlopen(f"{api}/sessions/{transcript.session_id}", timeout=15) as reply:
            view = json.load(reply)
    except OSError:
        return None
    return case_from_events(view["events"], transcript.session_id, tenant=tenant, project=project)


def case_from_events(
    events: Sequence[dict[str, Any]], session_id: str, *, tenant: str, project: str
) -> ConversationalTestCase:
    """The `/sessions/<id>` event view as the multi-turn case a consent metric reads."""
    return ConversationalTestCase(
        turns=replay.turns_from(
            [Event(**row) for row in events], replay.descriptions_for(tenant, project)
        ),
        name=session_id,
        scenario=replay.SCENARIO.format(channel="voice", tenant=tenant, project=project),
    )

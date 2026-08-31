"""The two personas, and everything about a ring-2 golden that can be decided without calling.

A live call costs a euro of providers and two minutes of wall clock, so
everything a run could get wrong for free is checked here: a persona that
sounds like the agent, a golden naming a policy nobody implements, a script
longer than its own `max_turns`, a language check that cannot tell the two
languages apart, and the log-to-case conversion the consent metric reads.
"""

import json
from pathlib import Path

import pytest
from deepeval.test_case import Turn

from core.registry import load_registry
from core.testing import deepeval as bridge
from core.testing import personas, ring2_goldens
from core.testing.ring2 import CALLER_VOICE, Transcript

pytestmark = pytest.mark.unit

PROJECTS = [
    ("clinica-norte", "reagendamiento"),
    ("tienda-sur", "pedidos"),
]


def goldens_of(tenant: str, project: str) -> list:
    return ring2_goldens.load(_evals(tenant, project) / "ring2_goldens.json")


def test_no_caller_sounds_like_any_project_on_this_fleet() -> None:
    voices = {persona.voice for persona in personas.PERSONAS.values()}
    spoken_by_projects = {
        project.voice for tenant in load_registry().values() for project in tenant.projects.values()
    }

    assert len(voices) == len(personas.PERSONAS), "two callers on one voice is one unreadable OGG"
    assert not voices & spoken_by_projects, "a caller answering in the agent's own voice"
    assert CALLER_VOICE not in spoken_by_projects, "and neither does the no-persona fallback"


def test_only_the_impatient_caller_interrupts() -> None:
    assert personas.APURADO.interrupts
    assert personas.APURADO.patience_s == pytest.approx(2.5)
    assert not personas.SPANGLISH.interrupts, "the code-switcher hears the answer out"


def test_the_code_switcher_leaves_the_tts_language_unset() -> None:
    unset = personas.SPANGLISH.language is None
    assert unset, "pinned to es, English comes out of ElevenLabs with Spanish vowels"
    assert personas.SPANGLISH.multilingual
    assert personas.APURADO.language == "es"


def test_a_persona_card_says_the_same_thing_in_deepevals_words() -> None:
    card = personas.APURADO.card()

    assert card.name == "apurado"
    assert card.voice == personas.APURADO.voice
    assert card.interruption_behavior is not None, "the simulator has to hear about the barge-in"
    assert personas.SPANGLISH.card().interruption_behavior is None
    assert personas.SPANGLISH.card().multilingual_stt


def test_an_unknown_persona_is_refused_by_name() -> None:
    with pytest.raises(LookupError, match="apurado, spanglish"):
        personas.persona("elderly")


@pytest.mark.parametrize(("tenant", "project"), PROJECTS)
def test_every_project_has_two_live_goldens_that_load(tenant: str, project: str) -> None:
    goldens = goldens_of(tenant, project)

    assert len(goldens) >= 2, "the card asks for at least two goldens per project"
    assert {golden.persona.name for golden in goldens} == set(personas.PERSONAS)
    for golden in goldens:
        assert golden.turns, f"{golden.name} says nothing out loud"
        assert len(golden.turns) <= golden.max_turns
        assert golden.policies, f"{golden.name} would call and check nothing"


@pytest.mark.parametrize(("tenant", "project"), PROJECTS)
def test_every_policy_a_golden_names_exists_on_that_project(tenant: str, project: str) -> None:
    metrics = bridge.project_metrics(tenant, project)

    for golden in goldens_of(tenant, project):
        for policy in golden.policies:
            factory, _source = ring2_goldens.POLICIES[policy]
            assert hasattr(metrics, factory), f"{tenant}/{project} has no {factory}()"


def test_a_policy_nobody_implements_is_refused_before_a_call_is_made() -> None:
    with pytest.raises(LookupError, match="grounded"):
        ring2_goldens.golden(_row(policies=["grounded"]))


def test_a_script_longer_than_its_own_cap_is_refused() -> None:
    with pytest.raises(AssertionError, match="max_turns=1"):
        ring2_goldens.golden(_row(turns=["una", "dos"], max_turns=1))


def test_consent_is_read_off_the_log_and_register_off_the_wire() -> None:
    assert ring2_goldens.POLICIES["consent"][1] == ring2_goldens.LOG, "no track carries a tool call"
    assert ring2_goldens.POLICIES["register"][1] == ring2_goldens.WIRE
    assert "grounded" not in ring2_goldens.POLICIES, "the log keeps result shapes, never contents"


def test_both_languages_are_only_reported_when_both_were_transcribed() -> None:
    mixed = _run(["hola, hi, I need to change mi cita del jueves"])
    spanish = _run(["hola, quiero cambiar mi cita del jueves"])

    assert mixed.languages_heard() == {"es", "en"}
    assert spanish.languages_heard() == {"es"}, "a Spanish-only call proves nothing about hints"


def test_a_code_switcher_heard_in_one_language_fails_the_run() -> None:
    run = _run(["hola, quiero cambiar mi cita"], persona="spanglish")

    assert "not Spanish AND English" in (run.out_of_character() or "")


def test_a_caller_nobody_interrupted_fails_the_barge_in_run() -> None:
    run = _run(["hola, quiero cambiar mi cita"], persona="apurado")

    assert "nothing was interrupted" in (run.out_of_character() or "")


def test_an_answer_that_never_came_fails_before_any_metric_is_paid_for() -> None:
    run = _run(["una", "dos"], persona="spanglish", answers=1)

    assert "the call did not finish" in (run.out_of_character() or "")


def test_the_event_log_becomes_the_case_the_consent_metric_reads() -> None:
    events = [
        {"seq": 1, "kind": "session.start", "t_ms": 0, "payload": {}},
        {"seq": 2, "kind": "turn.user", "t_ms": 900, "payload": {"text": "sí, cancélalo"}},
        {"seq": 3, "kind": "tool.call", "t_ms": 1200, "payload": {"tool": "cancel_order"}},
        {"seq": 4, "kind": "turn.agent", "t_ms": 2400, "payload": {"text": "Hecho, ya está."}},
    ]

    case = ring2_goldens.case_from_events(events, "job-1", tenant="tienda-sur", project="pedidos")

    assert [turn.role for turn in case.turns] == ["user", "assistant"]
    called = [tool.name for tool in case.turns[-1].tools_called or []]
    assert called == ["cancel_order"], "the graph asks whether the write ran; this is where it is"


def _run(
    heard: list[str], *, persona: str = "spanglish", answers: int | None = None
) -> ring2_goldens.LiveRun:
    """A finished run with nothing live behind it: the caller's turns are what STT heard."""
    golden = ring2_goldens.golden(_row(persona=persona, turns=heard, max_turns=len(heard)))
    transcript = Transcript(room="eval-x-y-1")
    for index, line in enumerate(heard):
        transcript.turns.append(Turn(role="user", content=line))
        if answers is None or index < answers:
            transcript.turns.append(Turn(role="assistant", content="Claro."))
    transcript.turns.insert(0, Turn(role="assistant", content="Clínica Norte, ¿dígame?"))
    return ring2_goldens.LiveRun(golden=golden, transcript=transcript)


def _row(**overrides) -> dict:
    row = {
        "name": "prueba",
        "persona": "apurado",
        "objective": "una llamada de prueba",
        "turns": ["hola"],
        "policies": ["register"],
        "max_turns": 4,
    }
    return {**row, **overrides}


def _evals(tenant: str, project: str) -> Path:
    root = Path(__file__).resolve().parent.parent
    return root / "tenants" / tenant / "projects" / project / "evals"


def test_the_goldens_files_are_json_a_person_can_edit() -> None:
    for tenant, project in PROJECTS:
        rows = json.loads((_evals(tenant, project) / "ring2_goldens.json").read_text())
        assert all(set(row) == set(_row()) for row in rows), "every golden has the same six fields"

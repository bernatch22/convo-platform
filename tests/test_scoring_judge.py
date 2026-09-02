"""Ring 4's paid half: the judge's gates, the sweeper, the CLI and the control plane's two doors."""

import pytest

from convo.cli import sessions as cli
from convo.scoring import runner, sweeper
from convo.scoring.rules import ScoringRules
from convo.state.events import Event
from convo.state.store import MemoryStore, SessionRow
from tests.fixtures.scoring import PROJECT, SESSION, TENANT, good_call, stored

pytestmark = pytest.mark.unit


# ── the judge's three gates ──────────────────────────────────────────────────


def two_turn_case():
    from deepeval.test_case import ConversationalTestCase, Turn

    return ConversationalTestCase(
        turns=[
            Turn(role="assistant", content="Clínica Norte, dígame."),
            Turn(role="user", content="perdón, me he equivocado"),
        ]
    )


def long_case(turns: int = 12):
    from deepeval.test_case import ConversationalTestCase, Turn

    line = "Le confirmo la cita para el jueves a las once de la mañana con la doctora. " * 20
    return ConversationalTestCase(
        turns=[Turn(role="assistant" if n % 2 else "user", content=line) for n in range(turns)]
    )


def test_a_call_under_three_turns_is_never_judged() -> None:
    from convo.scoring import judge as judge_module

    check, run = judge_module.judge(two_turn_case(), ScoringRules())

    assert check is None and run.ran is False
    assert "under 3 turns" in run.skipped


def test_the_cap_is_proved_before_the_call_is_made_not_after(monkeypatch) -> None:
    from convo.scoring import judge as judge_module

    monkeypatch.setattr(judge_module, "CAP_EUR", 0.0000001)
    monkeypatch.setattr(judge_module, "MAX_TURNS", 100)

    check, run = judge_module.judge(long_case(), ScoringRules())

    assert check is None and run.ran is False and "over the" in run.skipped


def test_a_longer_transcript_estimates_dearer_than_a_shorter_one() -> None:
    from convo.scoring import judge as judge_module

    assert judge_module.estimated_eur(long_case(20)) > judge_module.estimated_eur(long_case(4))


def test_the_transcript_is_cut_to_the_last_turns_before_it_is_priced() -> None:
    from convo.scoring import judge as judge_module

    trimmed = judge_module._trim(long_case(200), long_case(200).turns)

    assert len(trimmed.turns) == judge_module.MAX_TURNS
    assert all(len(t.content) <= judge_module.MAX_CHARS for t in trimmed.turns)


# ── the sweeper ─────────────────────────────────────────────────────────────


def test_the_sweeper_offers_finished_unscored_sessions_oldest_first() -> None:
    store = MemoryStore()
    for index, started in enumerate([300.0, 200.0], start=1):
        session_id = f"s{index}"
        store.open_session(SessionRow(session_id, TENANT, PROJECT, "voice", started_at=started))
        store.append(session_id, Event(1, "session.end", 10, {"outcome": "completed"}))

    assert sweeper.due(store, now=400.0) == ["s2", "s1"]


def test_the_sweeper_skips_a_session_that_already_carries_a_score() -> None:
    store = stored(good_call())
    runner.score_session(SESSION, store, judge=False)

    assert sweeper.due(store, now=200.0) == []


def test_a_sweep_scores_what_it_found_and_says_which(monkeypatch) -> None:
    monkeypatch.setattr(sweeper, "score_session", lambda sid, store: {"scored": True})
    store = stored(good_call())

    assert sweeper.tick(store, now=200.0) == [SESSION]


# ── what the CLI shows ──────────────────────────────────────────────────────


def test_sessions_show_prints_the_score_and_its_breakdown(capsys) -> None:
    store = stored(good_call())
    runner.score_session(SESSION, store, judge=False)

    cli.main(["show", SESSION], store)

    printed = capsys.readouterr().out
    assert "session.score" in printed and "pass" in printed
    assert "consent" in printed and "no_errors" in printed


def test_sessions_score_can_be_asked_for_by_hand_and_is_idempotent(capsys) -> None:
    store = stored(good_call())

    assert cli.main(["score", SESSION, "--free"], store) == 0
    assert cli.main(["score", SESSION, "--free"], store) == 0
    assert "already scored" in capsys.readouterr().out


# ── the control plane's two doors ───────────────────────────────────────────


def test_the_session_list_carries_the_score_the_console_draws_a_chip_from() -> None:
    from fastapi.testclient import TestClient

    from convo.api.app import app, open_store

    store = stored(good_call())
    runner.score_session(SESSION, store, judge=False)
    app.dependency_overrides[open_store] = lambda: store
    try:
        row = TestClient(app).get("/sessions").json()[0]
    finally:
        app.dependency_overrides.clear()

    assert row["score"]["verdict"] == "pass" and row["score"]["score"] == 1.0
    assert [check["name"] for check in row["score"]["checks"]][0] == "consent"


def test_an_unscored_session_says_null_rather_than_zero() -> None:
    from fastapi.testclient import TestClient

    from convo.api.app import app, open_store

    app.dependency_overrides[open_store] = lambda: stored(good_call())
    try:
        row = TestClient(app).get("/sessions").json()[0]
    finally:
        app.dependency_overrides.clear()

    assert row["score"] is None, "not yet scored is not a bad score"


def test_the_score_endpoint_writes_once_and_answers_the_same_thing_twice(
    tmp_path, monkeypatch
) -> None:
    from fastapi.testclient import TestClient

    from convo.api.app import app
    from convo.state.store import SQLiteStore

    monkeypatch.setenv("CONVO_DB", str(tmp_path / "convo.db"))
    monkeypatch.setenv("SCORING_SWEEP", "0")  # the route under test, not the background one
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")  # deterministic half only: the judge is skipped
    seed = SQLiteStore()
    seed.open_session(SessionRow(SESSION, TENANT, PROJECT, "voice", started_at=100.0))
    for event in good_call():
        seed.append(SESSION, event)
    seed.close_session(SESSION, "completed", None)

    with TestClient(app) as client:
        first = client.post(f"/sessions/{SESSION}/score").json()
        second = client.post(f"/sessions/{SESSION}/score").json()

    assert first["scored"] is True and second["scored"] is False
    assert first["score"]["verdict"] == second["score"]["verdict"] == "pass"
    assert [e.kind for e in SQLiteStore().events(SESSION)].count("session.score") == 1


def test_a_call_with_no_words_at_all_still_gets_its_free_checks_and_no_judge() -> None:
    """A hang-up before the first word: DeepEval refuses an empty-turns case, so the
    judge must be skipped BEFORE the case is built — the live sweeper wedged on that
    TypeError, retrying one silent call forever (found on the box, 2026-08-31)."""
    from convo.scoring.runner import build_report

    end = Event(2, "session.end", 900, {"outcome": "dropped"})
    events = [Event(1, "session.start", 0, {}), end]
    report = build_report("clinica-norte", "reagendamiento", events, "dropped", judge=True)
    assert report.turns == 0
    assert report.judge is None
    assert report.checks, "the deterministic checks must still stand"

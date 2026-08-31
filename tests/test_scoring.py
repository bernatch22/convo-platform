"""Ring 4: a finished call scores itself — the free checks, the capped judge, the log line.

Every test here is offline. The judge is never measured: what is asserted about
it is the three gates in front of it (too short, no key, over the cap), which is
where all its behaviour that can be wrong actually lives. Whether Haiku is a
good judge of a call is a question for `deepeval test run`, not for the fast
ring.
"""

import time

import pytest

from convo import sessions as cli
from core.context import Project, Tenant
from core.scoring import checks, report, runner, sweeper
from core.scoring.rules import ScoringRules, rules_for
from core.state.events import Event
from core.state.store import MemoryStore, SessionRow

pytestmark = pytest.mark.unit

SESSION = "sess-scored"
TENANT, PROJECT = "clinica-norte", "reagendamiento"


def turn(seq: int, role: str, text: str, t_ms: int | None = None) -> Event:
    return Event(seq, f"turn.{role}", t_ms if t_ms is not None else seq * 100, {"text": text})


def call(seq: int, tool: str, effect: str = "irreversible") -> Event:
    return Event(seq, "tool.call", seq * 100, {"tool": tool, "side_effect": effect})


def granted(seq: int, tool: str) -> Event:
    return Event(seq, "confirm.granted", seq * 100, {"tool": tool, "audience": f"{tool}:ab"})


def good_call() -> list[Event]:
    """A short, correct clinic call: consent asked and granted before the one write."""
    return [
        Event(1, "session.start", 0, {"tenant": TENANT}),
        turn(2, "agent", "Clínica Norte, buenos días, le atiende recepción."),
        turn(3, "user", "quería cambiar mi cita"),
        turn(4, "agent", "Por supuesto, ¿me dice su nombre?"),
        turn(5, "user", "Marta Alonso"),
        granted(6, "book_slot"),
        call(7, "book_slot"),
        turn(8, "agent", "Hecho, queda el jueves a las once."),
        Event(9, "session.end", 900, {"outcome": "completed", "cost": {"eur": 0.003}}),
    ]


def stored(
    events: list[Event],
    closed: bool = True,
    project: str = PROJECT,
    started_at: float = 100.0,
) -> MemoryStore:
    store = MemoryStore()
    store.open_session(SessionRow(SESSION, TENANT, project, "voice", started_at=started_at))
    for event in events:
        store.append(SESSION, event)
    if closed:
        store.close_session(SESSION, "completed", None)
    return store


def turns_of(events: list[Event]) -> list:
    from core.testing import replay

    return replay.turns_from(events)


# ── the deterministic checks ─────────────────────────────────────────────────


def test_an_irreversible_call_with_no_grant_before_it_fails_consent() -> None:
    check = checks.consent([turn(1, "user", "vale"), call(2, "book_slot")])

    assert check.passed is False
    assert "book_slot" in check.reason


def test_a_grant_before_the_write_passes_consent() -> None:
    assert checks.consent([granted(1, "book_slot"), call(2, "book_slot")]).passed is True


def test_a_second_write_needs_a_second_grant() -> None:
    events = [granted(1, "book_slot"), call(2, "book_slot"), call(3, "book_slot")]

    assert checks.consent(events).passed is False


def test_a_call_that_wrote_nothing_irreversible_passes_consent_vacuously() -> None:
    check = checks.consent([turn(1, "agent", "hola"), call(2, "find_patient", effect="read")])

    assert check.passed is True and check.reason == checks.NO_IRREVERSIBLE


def test_a_tu_form_in_an_agent_turn_fails_the_register_check() -> None:
    turns = turns_of([turn(1, "agent", "Claro, te lo miro ahora mismo.")])

    check = checks.register(turns, ("te", "tu"))

    assert check.passed is False and "«te»" in check.reason


def test_a_project_with_no_register_rule_is_not_applicable_rather_than_passed() -> None:
    check = checks.register(turns_of([turn(1, "agent", "hola")]), ())

    assert check.passed is None, "an unmeasured rule must never count as a pass"


def test_naming_the_business_next_door_fails_the_leakage_check() -> None:
    turns = turns_of([turn(1, "agent", "Eso es de Tienda Sur, llame al 954 000 000.")])

    check = checks.no_leakage(turns, ("Tienda Sur", "954 000 000"))

    # The scan flattens both sides — lowercase, accent-free — so the reason quotes
    # the flattened term, exactly as the ring-1 leakage node writes it.
    assert check.passed is False and "tienda sur" in check.reason


def test_an_error_event_fails_the_clean_run_check() -> None:
    events = [Event(1, "error", 10, {"source": "STT", "error": "websocket closed"})]

    assert checks.no_errors(events, "completed").passed is False


def test_an_outcome_of_error_fails_even_with_no_error_event() -> None:
    assert checks.no_errors([], "error").passed is False


# ── the arithmetic of a report ───────────────────────────────────────────────


def test_a_not_applicable_check_is_dropped_from_the_average() -> None:
    built = report.ScoreReport(
        checks=[
            report.Check("a", True, ""),
            report.Check("b", None, ""),
            report.Check("c", False, ""),
        ]
    )

    assert built.score() == 0.5, "two applicable checks, one passed"
    assert built.verdict() == "fail" and built.failed() == ["c"]


def test_the_judge_contributes_its_raw_score_not_a_rounded_verdict() -> None:
    built = report.ScoreReport(
        checks=[report.Check("a", True, ""), report.Check("j", True, "", report.JUDGE, score=0.8)]
    )

    assert built.score() == 0.9


# ── when a call counts as over ───────────────────────────────────────────────


def test_a_call_still_appending_is_not_finished() -> None:
    row = SessionRow(SESSION, TENANT, PROJECT, "voice", started_at=1000.0)
    events = [turn(1, "user", "hola", t_ms=0)]

    assert report.finished(row, events, now=1001.0) is False


def test_a_call_whose_log_has_gone_quiet_is_finished_even_with_no_close_event() -> None:
    row = SessionRow(SESSION, TENANT, PROJECT, "voice", started_at=1000.0)
    events = [turn(1, "user", "hola", t_ms=0)]

    assert report.finished(row, events, now=1000.0 + report.STALE_S + 1) is True


def test_a_closed_row_is_finished_whatever_its_log_ends_with() -> None:
    row = SessionRow(SESSION, TENANT, PROJECT, "voice", started_at=1000.0, outcome="dropped")

    assert report.finished(row, [turn(1, "user", "hola", t_ms=0)], now=1000.1) is True


# ── the score as a log line ──────────────────────────────────────────────────


def test_the_score_takes_the_next_seq_and_is_appended_never_edited() -> None:
    store = stored(good_call())

    result = runner.score_session(SESSION, store, judge=False)

    assert result["scored"] is True
    written = store.events(SESSION)[-1]
    assert written.kind == "session.score" and written.seq == 10
    assert written.payload["verdict"] == "pass"


def test_scoring_the_same_session_twice_writes_one_event() -> None:
    store = stored(good_call())
    runner.score_session(SESSION, store, judge=False)

    again = runner.score_session(SESSION, store, judge=False)

    assert again["scored"] is False and again["score"]["verdict"] == "pass"
    assert [e.kind for e in store.events(SESSION)].count("session.score") == 1


def test_a_running_call_is_refused_rather_than_scored_half_way() -> None:
    store = stored(good_call()[:4], closed=False, started_at=time.time())

    result = runner.score_session(SESSION, store, judge=False)

    assert result["scored"] is False and result["skipped"] == runner.STILL_RUNNING
    assert "session.score" not in [e.kind for e in store.events(SESSION)]


def test_a_session_that_is_not_in_the_store_is_refused_by_name() -> None:
    assert "no session" in runner.score_session("nope", MemoryStore())["skipped"]


def test_a_project_with_scoring_off_gets_no_score_event_at_all(monkeypatch) -> None:
    quiet = Project(id="quiet", name="Quiet queue", scoring=False)
    monkeypatch.setattr(
        runner,
        "load_registry",
        lambda: {TENANT: Tenant(id=TENANT, name="Clínica Norte", projects={"quiet": quiet})},
    )
    store = stored(good_call(), project="quiet")

    result = runner.score_session(SESSION, store, judge=False)

    assert result["skipped"] == runner.SCORING_OFF.format(tenant=TENANT, project="quiet")
    assert "session.score" not in [e.kind for e in store.events(SESSION)]


# ── the project's own rules ──────────────────────────────────────────────────


def test_the_clinic_declares_the_register_and_the_shop_it_must_not_name() -> None:
    rules = rules_for(TENANT, PROJECT)

    assert "te" in rules.forbidden_register
    assert "Tienda Sur" in rules.other_business
    assert rules.judge_steps, "the clinic writes its own judge steps"


def test_a_project_with_no_rules_file_is_scored_on_what_the_platform_can_decide() -> None:
    rules = rules_for("nobody", "nothing")

    assert rules == ScoringRules(), "missing rules are empty, never an exception"


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
    from core.scoring import judge as judge_module

    check, run = judge_module.judge(two_turn_case(), ScoringRules())

    assert check is None and run.ran is False
    assert "under 3 turns" in run.skipped


def test_the_cap_is_proved_before_the_call_is_made_not_after(monkeypatch) -> None:
    from core.scoring import judge as judge_module

    monkeypatch.setattr(judge_module, "CAP_EUR", 0.0000001)
    monkeypatch.setattr(judge_module, "MAX_TURNS", 100)

    check, run = judge_module.judge(long_case(), ScoringRules())

    assert check is None and run.ran is False and "over the" in run.skipped


def test_a_longer_transcript_estimates_dearer_than_a_shorter_one() -> None:
    from core.scoring import judge as judge_module

    assert judge_module.estimated_eur(long_case(20)) > judge_module.estimated_eur(long_case(4))


def test_the_transcript_is_cut_to_the_last_turns_before_it_is_priced() -> None:
    from core.scoring import judge as judge_module

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

    from api import app, open_store

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

    from api import app, open_store

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

    from api import app
    from core.state.store import SQLiteStore

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
    from core.scoring.runner import build_report

    events = [Event(1, "session.start", 0, {}), Event(2, "session.end", 900, {"outcome": "dropped"})]
    report = build_report("clinica-norte", "reagendamiento", events, "dropped", judge=True)
    assert report.turns == 0
    assert report.judge is None
    assert report.checks, "the deterministic checks must still stand"

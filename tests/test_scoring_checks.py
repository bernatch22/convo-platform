"""Ring 4's free half: the checks, the arithmetic, when a call is over, the score as a log line."""

import time

import pytest

from convo.domain.context import Project, Tenant
from convo.scoring import checks, report, runner
from convo.scoring.rules import ScoringRules, rules_for
from convo.state.events import Event
from convo.state.store import MemoryStore, SessionRow
from tests.fixtures.scoring import (
    PROJECT,
    SESSION,
    TENANT,
    call,
    good_call,
    granted,
    stored,
    turn,
    turns_of,
)

pytestmark = pytest.mark.unit


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

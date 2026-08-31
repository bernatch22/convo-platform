"""The one LLM call ring 4 is allowed to make, and the cap that is proved before it is made.

One metric, one model call, per finished call. Everything else in the score is
code, so this is the whole of the budget and the whole of the exposure — and it
is spent on the one question code genuinely cannot answer: did this call do for
the person what they rang up for?

Three gates stand in front of it, in the order they are cheapest to check:

1. **Under three turns, nothing is judged.** A wrong number, a hang-up on the
   greeting, a "perdón, me he equivocado" — there is no conversation to have an
   opinion about, and a judge handed one invents one. The deterministic checks
   still run; the score is theirs alone.
2. **The transcript is cut to the last `MAX_TURNS`, each turn to `MAX_CHARS`.**
   A forty-minute call and a two-minute call must cost the same to score, and
   the end of a call is where completion is visible.
3. **The worst case is priced before it is bought.** Input estimated from the
   rendered prompt, output assumed at its ceiling, both at the same
   `core.observability.prices` table `session.end` is priced with. Over the cap
   → the judge does not run and the log says so, with both numbers.

The euros written into `session.score` are then the REAL ones, from the token
counts DeepEval reports back, not the estimate: the estimate exists to refuse,
the measurement to audit.

Open source note: `ConversationalGEval` with explicit `evaluation_steps` is the
whole trick to a one-call judge — leave the steps out and DeepEval spends a
second model call generating them, on every session, forever.
"""

import logging
import os

from core.observability.prices import MTOK, PRICES, USD_EUR
from core.scoring.report import JUDGE, Check, JudgeRun
from core.scoring.rules import ScoringRules

log = logging.getLogger("platform.scoring")

MODEL = os.getenv("SCORING_JUDGE_MODEL", "claude-haiku-4-5")
CAP_EUR = float(os.getenv("SCORING_CAP_EUR", "0.01"))
THRESHOLD = float(os.getenv("SCORING_JUDGE_THRESHOLD", "0.7"))

MIN_TURNS = 3
MAX_TURNS = 40
MAX_CHARS = 400
# Spanish runs shorter per token than English; 3.5 chars/token is the
# conservative direction, and the estimate only ever has to refuse safely.
CHARS_PER_TOKEN = 3.5
TEMPLATE_TOKENS = 900
ASSUMED_OUTPUT_TOKENS = 500

NAME = "Call quality"
TOO_SHORT = "under {min} turns ({turns}): there is no conversation to judge"
TOO_DEAR = "estimated {estimate:.4f} € is over the {cap:.4f} € cap for one call"
NO_KEY = "ANTHROPIC_API_KEY is not set on the control plane"
UNAVAILABLE = "the judge could not be reached: {error}"

# The platform default, overridable per project in `evals/scoring.py`. Written as
# steps rather than as prose because a GEval given only criteria spends a model
# call turning them into steps — and then paraphrases them differently each run.
DEFAULT_STEPS = (
    "Read the whole conversation and decide what the person rang up for. If they never "
    "made it clear, say so and judge only whether the agent tried to find out.",
    "Check whether the agent actually did it, or told them plainly that it could not and "
    "what they should do instead. Both count as done; only leaving them without either is not.",
    "Penalise an agent that ignored a question, repeated itself in circles, or ended the "
    "call with the person's request still hanging in the air.",
    "Do not judge tone, register, or whether the facts stated were true — other checks own "
    "those and marking them twice here would double a single fault.",
    "Score 10 when the person got what they rang for or a clear honest no, 5 when it was "
    "half done, 0 when the call left them where it found them.",
)


def judge(case, rules: ScoringRules) -> tuple[Check | None, JudgeRun]:
    """Score one replayed call with the single judged metric, or say why it was not.

    Returns the check to add to the report (None when nothing was judged) and
    the `JudgeRun` that goes into the log either way: a skip is an audited
    event, not a silence.
    """
    turns = _judgeable(case.turns)
    if len(turns) < MIN_TURNS:
        return None, _skipped(TOO_SHORT.format(min=MIN_TURNS, turns=len(turns)))
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None, _skipped(NO_KEY)

    trimmed = _trim(case, turns)
    estimate = estimated_eur(trimmed)
    if estimate > CAP_EUR:
        return None, _skipped(TOO_DEAR.format(estimate=estimate, cap=CAP_EUR))

    try:
        return _measure(trimmed, rules)
    except Exception as error:  # noqa: BLE001 — a judge that is down must not lose the free checks
        log.exception("the post-call judge failed; the deterministic checks stand alone")
        return None, _skipped(UNAVAILABLE.format(error=type(error).__name__))


def estimated_eur(case) -> float:
    """What this case would cost at worst: the rendered turns in, the ceiling out.

    Priced from the same table `session.end` uses, so the euros in a score and
    the euros in a bill are the same currency measured the same way. An unpriced
    model estimates as free — and is then reported as it really cost, never
    guessed at.
    """
    price = PRICES.get(MODEL)
    if price is None:
        return 0.0
    characters = sum(len(turn.content or "") + len(turn.role or "") for turn in case.turns)
    tokens_in = characters / CHARS_PER_TOKEN + TEMPLATE_TOKENS
    return (tokens_in * price.input + ASSUMED_OUTPUT_TOKENS * price.output) / MTOK


def cost_eur(metric) -> float:
    """What the judge really cost, from the tokens DeepEval counted; its own USD as a fallback."""
    price = PRICES.get(MODEL)
    tokens_in = getattr(metric, "input_tokens", None)
    tokens_out = getattr(metric, "output_tokens", None)
    if price and isinstance(tokens_in, int) and isinstance(tokens_out, int):
        return (tokens_in * price.input + tokens_out * price.output) / MTOK
    return float(getattr(metric, "evaluation_cost", 0.0) or 0.0) * USD_EUR


def _measure(case, rules: ScoringRules) -> tuple[Check, JudgeRun]:
    """Build the metric, run it once, and turn its 0-1 into a check and a bill."""
    from deepeval.metrics import ConversationalGEval
    from deepeval.models import AnthropicModel
    from deepeval.test_case import MultiTurnParams

    metric = ConversationalGEval(
        name=rules.judge_name or NAME,
        evaluation_steps=list(rules.judge_steps or DEFAULT_STEPS),
        # Role and content only. The tools are already judged, for free and
        # without opinion, by `checks.consent`; putting them in front of a judge
        # buys a second verdict on the same fact and pays for the tokens twice.
        evaluation_params=[MultiTurnParams.ROLE, MultiTurnParams.CONTENT],
        model=AnthropicModel(model=MODEL),
        threshold=THRESHOLD,
        # Sync: this runs inside a worker thread of the control plane, and one
        # metric has nothing to overlap with. `async_mode` would spin up an
        # event loop per session to await a single request.
        async_mode=False,
    )
    value = float(metric.measure(case))
    spent = cost_eur(metric)
    check = Check(
        name="call_quality",
        passed=value >= THRESHOLD,
        reason=str(metric.reason or "no reason given"),
        kind=JUDGE,
        score=value,
    )
    return check, JudgeRun(True, MODEL, THRESHOLD, CAP_EUR, cost_eur=spent)


def _judgeable(turns: list) -> list:
    """Turns with something said in them: a silent marker turn is not a turn of a call."""
    return [turn for turn in turns if (turn.content or "").strip()]


def _trim(case, turns: list):
    """The last `MAX_TURNS` turns, each cut to `MAX_CHARS`, as a fresh case to judge.

    A fresh case rather than an edit: the one the caller holds is the log's own
    reading of the call and other metrics read it afterwards.
    """
    from deepeval.test_case import ConversationalTestCase, Turn

    kept = turns[-MAX_TURNS:]
    return ConversationalTestCase(
        turns=[Turn(role=turn.role, content=_cut(turn.content or "")) for turn in kept],
        name=case.name,
        scenario=case.scenario,
    )


def _cut(text: str) -> str:
    return text if len(text) <= MAX_CHARS else text[: MAX_CHARS - 1] + "…"


def _skipped(reason: str) -> JudgeRun:
    return JudgeRun(False, MODEL, THRESHOLD, CAP_EUR, skipped=reason)

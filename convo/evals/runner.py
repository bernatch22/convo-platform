"""Run one project's eval suite on the box: one subprocess at a time, killed at fifteen minutes.

Decisions: docs/decisions/convo.evals.runner.md
"""

import asyncio
import contextlib
import json
import os
import sys
import time
import uuid
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from dotenv import dotenv_values

from convo.evals.runs import DONE, FAILED
from convo.session.router import git_sha
from convo.state.store import EvalRun, MetricScore, Store

DEADLINE_S = 15 * 60
LOG_DIR = Path("tmp/evals")
TAIL_LINES = 60
REPO_ROOT = Path(__file__).resolve().parents[2]


class EvalRunBusy(RuntimeError):
    """A run was asked for while another was alive; the message names the one holding the box."""


def deepeval_command(target: str) -> list[str]:
    """`deepeval test run <target>`, from the same virtualenv that is running this process."""
    binary = Path(sys.executable).parent / "deepeval"
    return [str(binary) if binary.exists() else "deepeval", "test", "run", target]


class EvalRunner:
    """The box's single eval slot: start a suite, watch it, store what it scored."""

    def __init__(
        self,
        open_store: Callable[[], Store],
        launcher: Callable[[str], list[str]] = deepeval_command,
        deadline_s: float = DEADLINE_S,
        log_dir: Path = LOG_DIR,
    ) -> None:
        self.open_store = open_store
        self.launcher = launcher
        self.deadline_s = deadline_s
        self.log_dir = log_dir
        self._running: str | None = None
        self._task: asyncio.Task[None] | None = None

    @property
    def busy(self) -> bool:
        """Is a run alive right now? The one thing the console asks before offering the button."""
        return self._running is not None

    @property
    def running(self) -> str | None:
        """The id of the run holding the box, or None."""
        return self._running

    async def start(self, tenant: str, project: str, suite: str, target: str) -> EvalRun:
        """Spawn `deepeval` for one project's suite, stored as running; refuses a second one."""
        if self._running is not None:
            raise EvalRunBusy(f"run {self._running} is still going; this box runs one at a time")
        run_id = run_stamp()
        run = EvalRun(
            id=run_id,
            tenant=tenant,
            project=project,
            suite=suite,
            started_at=time.time(),
            git_sha=git_sha(),
            log_path=str(self.log_dir / f"{run_id}.log"),
        )
        self._running = run.id
        self._store(run)
        self._task = asyncio.create_task(self._supervise(run, target))
        return run

    def tail(self, run: EvalRun, lines: int = TAIL_LINES) -> list[str]:
        """The last lines the run wrote, for the console to show while it is still going."""
        if not run.log_path:
            return []
        path = Path(run.log_path)
        if not path.is_file():
            return []
        return path.read_text(errors="replace").splitlines()[-lines:]

    async def _supervise(self, run: EvalRun, target: str) -> None:
        """Wait for the child, kill it at the deadline, and store the verdict either way."""
        results = self.log_dir / run.id
        log = Path(run.log_path or "")
        log.parent.mkdir(parents=True, exist_ok=True)
        process: asyncio.subprocess.Process | None = None
        try:
            with log.open("w") as sink:
                process = await asyncio.create_subprocess_exec(
                    *self.launcher(target),
                    stdout=sink,
                    stderr=asyncio.subprocess.STDOUT,
                    cwd=REPO_ROOT,
                    env=child_env(results),
                )
                code = await asyncio.wait_for(process.wait(), self.deadline_s)
            detail = None if code == 0 else f"the suite exited {code} — read the log"
            self._finish(run, DONE if code == 0 else FAILED, results, detail)
        except TimeoutError:
            await _kill(process)
            self._finish(run, FAILED, results, f"killed after {self.deadline_s:.0f}s")
        except OSError as error:
            self._finish(run, FAILED, results, f"could not start deepeval: {error}")
        finally:
            self._running = None

    def _finish(self, run: EvalRun, status: str, results: Path, detail: str | None) -> None:
        """Store the run's end — with the scores, because a FAILING suite still scored something."""
        self._store(
            replace(
                run,
                status=status,
                finished_at=time.time(),
                metrics=metrics_of(results),
                detail=detail,
            )
        )

    def _store(self, run: EvalRun) -> None:
        self.open_store().add_eval_run(run)


def child_env(results: Path) -> dict[str, str]:
    """The box's environment, the `.env` keys the suite needs, and where to drop its scores."""
    loaded = dotenv_values(REPO_ROOT / ".env")
    env = {key: value for key, value in loaded.items() if value is not None}
    env.update(os.environ)
    env["DEEPEVAL_RESULTS_FOLDER"] = str(results)
    env["DEEPEVAL_TELEMETRY_OPT_OUT"] = "YES"
    return env


def metrics_of(results: Path) -> tuple[MetricScore, ...]:
    """Per-metric scores out of the newest `test_run_*.json` deepeval wrote; () when none."""
    written = sorted(results.glob("test_run_*.json")) if results.is_dir() else []
    if not written:
        return ()
    try:
        data = json.loads(written[-1].read_text())
    except (OSError, json.JSONDecodeError):
        return ()
    return tuple(_score(row) for row in data.get("metricsScores", []) if row.get("metric"))


def run_stamp() -> str:
    """A run id that sorts by time and names its own log: `ev-<YYYYmmdd-HHMMSS>-<hex>`."""
    return "ev-" + time.strftime("%Y%m%d-%H%M%S") + f"-{uuid.uuid4().hex[:4]}"


def _score(row: dict) -> MetricScore:
    scores = [value for value in row.get("scores", []) if isinstance(value, (int, float))]
    mean = round(sum(scores) / len(scores), 4) if scores else 0.0
    return MetricScore(
        metric=str(row["metric"]),
        score=mean,
        passed=int(row.get("passes", 0)),
        failed=int(row.get("fails", 0)) + int(row.get("errors", 0)),
    )


async def _kill(process: asyncio.subprocess.Process | None) -> None:
    """Kill a child that ran past the deadline and wait for it, so no zombie is left behind."""
    if process is None:
        return
    with contextlib.suppress(ProcessLookupError):
        process.kill()
    await process.wait()

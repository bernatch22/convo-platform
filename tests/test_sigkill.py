"""A process killed mid-call leaves every event it had appended, contiguous up to the last seq."""

import os
import signal
import subprocess
import sys
import textwrap

import pytest

from core.state.store import SQLiteStore

pytestmark = pytest.mark.unit

WRITER = textwrap.dedent(
    """
    import os, signal, sys
    from core.state.attach import attach_log
    from core.state.store import SQLiteStore
    from core.testing import fake_context
    store = SQLiteStore(sys.argv[1])
    tc = fake_context("clinica-norte", "reagendamiento")
    tc.session_id = "killed"
    attach_log(tc, store)
    for i in range(50):
        tc.log.append("tool.call", {"tool": "find_availability", "i": i})
        if i == 29:
            os.kill(os.getpid(), signal.SIGKILL)
    """
)


def test_every_seq_written_before_sigkill_is_readable_and_contiguous(tmp_path) -> None:
    db = tmp_path / "convo.db"
    proc = subprocess.run(
        [sys.executable, "-c", WRITER, str(db)],
        cwd=os.getcwd(),
        env={**os.environ, "PYTHONPATH": os.getcwd()},
        capture_output=True,
        timeout=60,
    )
    assert proc.returncode == -signal.SIGKILL, proc.stderr.decode()[-500:]

    events = SQLiteStore(db).events("killed")
    seqs = [e.seq for e in events]
    assert seqs == list(range(1, 32)), "session.start + thirty tool.call, no gaps"
    assert events[-1].payload["i"] == 29

"""The repo shape, enforced: no loose entry points, no long files, no livekit in a tenant."""

import pathlib
import re
import subprocess

import pytest

pytestmark = pytest.mark.unit

ROOT = pathlib.Path(__file__).resolve().parents[1]
LINE_LIMIT = 400
LIVEKIT_IMPORT = re.compile(r"^\s*(from|import)\s+livekit\b", re.MULTILINE)


def tracked_python() -> list[pathlib.Path]:
    """Every .py file git knows about, so an untracked scratch file cannot fail the suite."""
    out = subprocess.run(
        ["git", "ls-files", "*.py"], cwd=ROOT, capture_output=True, text=True, check=True
    )
    return [ROOT / line for line in out.stdout.split()]


def test_no_python_file_sits_at_the_repo_root() -> None:
    loose = [path.name for path in tracked_python() if path.parent == ROOT]
    assert loose == [], f"entry points belong under convo/: {loose}"


def test_no_tracked_python_file_is_over_four_hundred_lines() -> None:
    long_files = {
        str(path.relative_to(ROOT)): count
        for path in tracked_python()
        if (count := len(path.read_text().splitlines())) > LINE_LIMIT
    }
    assert long_files == {}, f"split before it grows: {long_files}"


def test_a_tenant_never_imports_the_agent_framework_directly() -> None:
    offenders = [
        str(path.relative_to(ROOT))
        for path in tracked_python()
        if path.relative_to(ROOT).parts[0] == "tenants" and LIVEKIT_IMPORT.search(path.read_text())
    ]
    assert offenders == [], f"projects import convo.agents, never livekit: {offenders}"

"""`convo` must never import `tenants`: a broken tenant cannot take the runtime down."""

import pathlib
import re

import pytest

pytestmark = pytest.mark.unit

CORE = pathlib.Path(__file__).resolve().parents[1] / "convo"
FORBIDDEN = re.compile(r"^\s*(from|import)\s+tenants\b", re.MULTILINE)


def test_convo_never_imports_tenants() -> None:
    offenders = [p for p in CORE.rglob("*.py") if FORBIDDEN.search(p.read_text())]
    assert offenders == [], f"convo imports tenants in: {offenders}"

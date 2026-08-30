"""tenants/_template is a working tenant: copied and renamed, it routes, runs and scores.

A template that only compiles is a template that has already rotted. This test
does what its README tells a stranger to do — copy the folder, substitute the
id — and then asks the platform the questions a real tenant has to answer: is
it in the registry, does a job route to it, does it declare tools an adapter can
actually serve, do its prompts render, do its goldens parse, does its register
scan work.

Nothing here calls a model. The template's value is that the LLM-free half of a
tenant is already correct before anybody writes a prompt.

The copy is removed in `finally`, `sys.modules` included: `tenants.<id>` is a
real package once imported, and a leftover one would make the next run pass for
the wrong reason.
"""

import importlib
import json
import pathlib
import shutil
import sys
from dataclasses import dataclass

import pytest

from core import registry, router
from core.state.store import MemoryStore
from core.testing.fake_job import fake_job_context
from core.testing.register import slips

pytestmark = pytest.mark.unit

TEMPLATE_ID = "example-co"
TENANT_ID = "zz-template-test"
PROJECT_ID = "example"
META = json.dumps({"tenant": TENANT_ID, "project": PROJECT_ID, "channel": "chat"})


@dataclass
class FakeTurn:
    """Enough of a deepeval Turn for the register scan: who spoke, and what they said."""

    role: str
    content: str


@pytest.fixture
def copied_template():
    """The template copied in as `zz-template-test`, exactly as its README says to."""
    source = registry.TENANTS_DIR / "_template"
    target = registry.TENANTS_DIR / TENANT_ID
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__"))
    for path in target.rglob("*.py"):
        path.write_text(path.read_text().replace(TEMPLATE_ID, TENANT_ID))
    importlib.invalidate_caches()
    try:
        yield target
    finally:
        shutil.rmtree(target, ignore_errors=True)
        for name in [n for n in sys.modules if n.startswith(f"tenants.{TENANT_ID}")]:
            del sys.modules[name]
        assert not pathlib.Path(target).exists()


async def test_the_copied_template_is_a_tenant_a_job_can_be_routed_to(copied_template) -> None:
    tenant = registry.load_registry()[TENANT_ID]

    tc = await router.resolve(fake_job_context(metadata=META), MemoryStore())

    assert (tc.tenant.id, tc.project.id, tc.channel) == (TENANT_ID, PROJECT_ID, "chat")
    assert tc.tools is not None and tc.log is not None
    assert tenant.name == "Example Co"


async def test_every_tool_it_declares_has_a_system_that_can_serve_it(copied_template) -> None:
    tc = await router.resolve(fake_job_context(metadata=META), MemoryStore())
    served = {name for adapter in tc.adapters.values() for name in adapter.capabilities()}

    declared = set(tc.project.tools.names())

    assert declared, "the template declares no tools at all"
    assert declared <= served, f"declared with no adapter: {sorted(declared - served)}"


async def test_its_prompts_render_with_the_knowledge_block_in_front(copied_template) -> None:
    tc = await router.resolve(fake_job_context(metadata=META), MemoryStore())

    stages = tc.project.stages(tc)

    assert [type(stage).__name__ for stage in stages] == ["Reception", "Desk"]
    for stage in stages:
        assert stage.instructions.startswith("<business_knowledge>")
        assert "INFORMACIÓN DE LA EMPRESA" in stage.instructions


def test_its_goldens_parse_and_carry_what_a_metric_reads(copied_template) -> None:
    goldens = json.loads((_evals(copied_template) / "goldens.json").read_text())

    assert goldens
    for golden in goldens:
        assert golden["input"] and golden["expected_behaviour"]


def test_its_register_scan_catches_a_slip_and_leaves_a_correct_reply_alone(
    copied_template,
) -> None:
    dag = importlib.import_module(f"tenants.{TENANT_ID}.projects.{PROJECT_ID}.evals.dag")
    correct = [FakeTurn("assistant", "Su reserva está activa. ¿Quiere que la cancele?")]
    slipped = [FakeTurn("assistant", "Tu reserva está activa, ¿quieres que la cancele?")]

    assert slips(correct, dag.TU_FORMS) == []
    assert slips(slipped, dag.TU_FORMS) == [(0, "tu"), (0, "quieres")]


def _evals(target: pathlib.Path) -> pathlib.Path:
    """Where the copied template keeps its goldens."""
    return target / "projects" / PROJECT_ID / "evals"

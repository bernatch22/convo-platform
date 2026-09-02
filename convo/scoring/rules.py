"""ScoringRules: the short list a project writes so its finished calls can be scored.

Decisions: docs/decisions/convo.scoring.rules.md
"""

import importlib
import logging
from dataclasses import dataclass
from types import ModuleType

log = logging.getLogger("platform.scoring")

RULES_MODULE = "scoring"
RULES_ATTR = "RULES"


@dataclass(frozen=True)
class ScoringRules:
    """What one project's calls are measured against once they have ended."""

    forbidden_register: tuple[str, ...] = ()
    other_business: tuple[str, ...] = ()
    judge_steps: tuple[str, ...] = ()
    judge_name: str = "Call quality"


NO_RULES = ScoringRules()


def rules_for(tenant_id: str, project_id: str) -> ScoringRules:
    """The project's own `evals/scoring.py:RULES`, or the empty default."""
    module = _module(tenant_id, project_id)
    if module is None:
        return NO_RULES
    rules = getattr(module, RULES_ATTR, None)
    if not isinstance(rules, ScoringRules):
        log.warning("%s/%s: evals.%s has no %s", tenant_id, project_id, RULES_MODULE, RULES_ATTR)
        return NO_RULES
    return rules


def _module(tenant_id: str, project_id: str) -> ModuleType | None:
    """Import one project's scoring rules by name; None when there are none to import."""
    name = f"tenants.{tenant_id}.projects.{project_id}.evals.{RULES_MODULE}"
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError:
        return None  # a project may simply not declare any: that is not an error
    except Exception:  # noqa: BLE001 — one bad eval package must not stop the scorer
        log.exception("%s failed to import; scored on platform rules alone", name)
        return None

"""ScoringRules: the short list a project writes so its finished calls can be scored.

A post-call score asks four questions of code and one of a judge, and three of
the five need words only the business owns: the register it speaks in, the
nouns that belong to the shop next door, and what "a good call" means here.
That is what this dataclass carries, and a project declares it in
`tenants/<id>/projects/<p>/evals/scoring.py` next to its goldens.

Loaded the way `core.registry` loads a tenant — by name, at call time, inside a
try/except — so a project with no rules file is scored on what the platform can
decide alone instead of taking the scorer down, and `core/` still compiles with
no customer folder on disk.

Deliberately free of `deepeval`: this module is imported by the projects
themselves and by the deterministic path, which must not pay for a judge stack
to find out that a call said "te" to a patient.
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
    """What one project's calls are measured against once they have ended.

    Every field is optional and an empty one disables its check rather than
    failing it: a project that declares no forbidden register is reported as
    "not applicable", never as "passed", because the two are different facts
    and only one of them is worth acting on.
    """

    forbidden_register: tuple[str, ...] = ()
    other_business: tuple[str, ...] = ()
    judge_steps: tuple[str, ...] = ()
    judge_name: str = "Call quality"


NO_RULES = ScoringRules()


def rules_for(tenant_id: str, project_id: str) -> ScoringRules:
    """The project's own `evals/scoring.py:RULES`, or the empty default.

    A missing file, a broken import or an attribute of the wrong type all mean
    the same thing to the scorer — this project told us nothing — and all of
    them are logged once and survived. A tenant whose eval package does not
    import must not stop the platform scoring everybody else's calls.
    """
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

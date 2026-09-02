"""Registry of tenants found under tenants/. A broken tenant is unroutable, never fatal.

Decisions: docs/decisions/convo.session.registry.md
"""

import importlib
import logging
import pathlib

from convo.domain.context import Tenant

log = logging.getLogger("platform.registry")

TENANTS_PACKAGE = "tenants"
TENANTS_DIR = pathlib.Path(__file__).resolve().parents[2] / TENANTS_PACKAGE


def load_registry() -> dict[str, Tenant]:
    """Import every tenants/<id>/tenant.py that exposes TENANT; skip (and log) the broken ones."""
    registry: dict[str, Tenant] = {}
    for folder in sorted(TENANTS_DIR.iterdir()):
        if not folder.is_dir() or folder.name.startswith("_") or folder.name.startswith("."):
            continue
        tenant = _import_tenant(folder.name)
        if tenant is not None:
            registry[tenant.id] = tenant
    return registry


def _import_tenant(name: str) -> Tenant | None:
    module_name = f"{TENANTS_PACKAGE}.{name}.tenant"
    try:
        return importlib.import_module(module_name).TENANT
    except Exception:  # noqa: BLE001 — one bad tenant must not take the fleet down
        log.exception("tenant %s failed to import; marked unroutable", name)
        return None

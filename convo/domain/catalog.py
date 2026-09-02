"""ToolCatalog: which tools a project may call, by name, plus the platform's own specs.

Decisions: docs/decisions/convo.domain.catalog.md
"""

from dataclasses import dataclass, field

from convo.domain.tools import SideEffect, ToolSpec

FIND_AVAILABILITY = ToolSpec(
    name="find_availability",
    side_effect=SideEffect.READ,
    timeout_s=5.0,
)

# `TenantAgent.fecha_y_hora_actual` — the name lives here so `core.dates_note`,
# which writes the session's clock reading into the chat context, and the eval
# bridge, which must not count it, read one declaration instead of two strings.
CLOCK = ToolSpec(
    name="fecha_y_hora_actual",
    side_effect=SideEffect.READ,
    timeout_s=1.0,
    infrastructure=True,
)


@dataclass(frozen=True)
class ToolCatalog:
    """The tools one project declares: a ToolSpec per name, looked up on every call."""

    specs: dict[str, ToolSpec] = field(default_factory=dict)

    @classmethod
    def of(cls, *specs: ToolSpec) -> "ToolCatalog":
        """Build a catalog from the specs themselves, keyed by `spec.name`."""
        return cls({spec.name: spec for spec in specs})

    def get(self, name: str) -> ToolSpec | None:
        """The spec of one tool, or None when this project does not declare it."""
        return self.specs.get(name)

    def names(self) -> list[str]:
        """Every declared tool name, sorted — the list a refusal quotes back."""
        return sorted(self.specs)

    def merge(self, other: "ToolCatalog") -> "ToolCatalog":
        """A new catalog with `other`'s specs layered on top of this one's."""
        return ToolCatalog({**self.specs, **other.specs})


def platform_specs() -> ToolCatalog:
    """The tools every project inherits from the platform; a tenant layers its own on top."""
    return ToolCatalog.of(FIND_AVAILABILITY)


def infrastructure_specs() -> ToolCatalog:
    """The platform's own tools: on every agent, in no project's catalog, nobody's business."""
    return ToolCatalog.of(CLOCK)


def infrastructure_names(*catalogs: ToolCatalog) -> frozenset[str]:
    """Every tool DECLARED as infrastructure — the platform's, plus any a project marks."""
    return frozenset(
        spec.name
        for catalog in (infrastructure_specs(), *catalogs)
        for spec in catalog.specs.values()
        if spec.infrastructure
    )

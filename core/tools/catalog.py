"""ToolCatalog: which tools a project may call, by name, plus the platform's own specs.

A catalog is data, not behaviour: the executor looks a name up here before it
guards, times or runs anything. A project that does not declare a tool cannot
call it, however convincing the model is about wanting to.

Two catalogs come from the platform and they are not the same thing.
`platform_specs()` is what a project INHERITS and may merge into its own: real
tools, run by the executor against the tenant's adapters. `infrastructure_specs()`
is the platform's own plumbing — the clock every `TenantAgent` carries — which
no project declares, no adapter backs and the executor never sees, because
livekit runs it as a plain `@function_tool` on the agent. It is declared here
anyway, and marked `infrastructure=True`, so that everything downstream can ask
a tool whether it belongs to the business instead of matching its name.
"""

from dataclasses import dataclass, field

from core.tools.contract import SideEffect, ToolSpec

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
    """The platform's own tools: on every agent, in no project's catalog, nobody's business.

    Deliberately NOT merged into `platform_specs()`. A project's catalog is the
    list of names the executor will accept, and the clock never reaches the
    executor — putting it there would promise a call the platform cannot route.
    """
    return ToolCatalog.of(CLOCK)


def infrastructure_names(*catalogs: ToolCatalog) -> frozenset[str]:
    """Every tool DECLARED as infrastructure — the platform's, plus any a project marks.

    Derived from the flag, never from a list of names written somewhere else:
    a project that adds plumbing of its own marks the spec and this answer grows
    with it. Callers that only care about the platform's pass nothing.
    """
    return frozenset(
        spec.name
        for catalog in (infrastructure_specs(), *catalogs)
        for spec in catalog.specs.values()
        if spec.infrastructure
    )

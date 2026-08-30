"""ToolCatalog: which tools a project may call, by name, plus the platform's own specs.

A catalog is data, not behaviour: the executor looks a name up here before it
guards, times or runs anything. A project that does not declare a tool cannot
call it, however convincing the model is about wanting to.
"""

from dataclasses import dataclass, field

from core.tools.contract import SideEffect, ToolSpec

FIND_AVAILABILITY = ToolSpec(
    name="find_availability",
    side_effect=SideEffect.READ,
    timeout_s=5.0,
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

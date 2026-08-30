"""Example project — replace with your use case."""

from dataclasses import dataclass

from core.context import Project, TenantContext


@dataclass
class ExampleProject(Project):
    """A project needs an entry agent; everything else is optional."""

    def entry_agent(self, tc: TenantContext):
        """First stage of the conversation."""
        from .agents import Welcome

        return Welcome(tc)


PROJECT = ExampleProject(id="example", name="Example")

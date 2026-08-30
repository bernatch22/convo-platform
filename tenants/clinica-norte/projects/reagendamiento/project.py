"""Reagendamiento: reschedule an existing appointment (ms-1: reception only, no tools)."""

from dataclasses import dataclass

from core.context import Project, TenantContext


@dataclass
class ReagendamientoProject(Project):
    """Project with an entry agent factory; voice and keyterms arrive with later milestones."""

    def entry_agent(self, tc: TenantContext):
        """The first stage a caller meets."""
        from .agents import Reception

        return Reception(tc)


PROJECT = ReagendamientoProject(
    id="reagendamiento",
    name="Reagendamiento de citas",
    language="es-ES",
    voice="UOIqAnmS11Reiei1Ytkc",  # ElevenLabs "Carolina - Spanish woman - es_ES" (used from ms-6)
)

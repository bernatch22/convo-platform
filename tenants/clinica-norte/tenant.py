"""Clínica Norte — demo tenant: appointment rescheduling for a medical clinic in Spain."""

from dataclasses import dataclass

from core.adapters.base import Adapter
from core.context import Tenant

from .projects.reagendamiento.project import PROJECT


@dataclass
class ClinicaNorteTenant(Tenant):
    """The clinic and the systems it runs; today the agenda is a fake, the seam is real."""

    def build_adapters(self) -> dict[str, Adapter]:
        """One adapter per system the clinic owns, built fresh for each session."""
        from .adapters.agenda import FakeAgenda

        return {"agenda": FakeAgenda()}


TENANT = ClinicaNorteTenant(
    id="clinica-norte",
    name="Clínica Norte",
    region="eu",
    projects={PROJECT.id: PROJECT},
)

"""Clínica Norte — demo tenant: appointment rescheduling for a medical clinic in Spain."""

from dataclasses import dataclass

from core.adapters.base import Adapter
from core.context import Tenant

from .projects.reagendamiento.project import PROJECT


@dataclass
class ClinicaNorteTenant(Tenant):
    """The clinic and the systems it runs; today they are fakes, the seam is real."""

    def build_adapters(self) -> dict[str, Adapter]:
        """One adapter per system the clinic owns, built fresh for each session.

        Two of them from ms-3 on: the appointment book and the SMS gateway. The
        executor picks whichever one declares the capability a tool asks for, so
        adding a system is adding a line here — no stage and no tool changes.
        """
        from .adapters.agenda import FakeAgenda
        from .adapters.sms import FakeSms

        return {"agenda": FakeAgenda(), "sms": FakeSms()}


TENANT = ClinicaNorteTenant(
    id="clinica-norte",
    name="Clínica Norte",
    region="eu",
    projects={PROJECT.id: PROJECT},
)

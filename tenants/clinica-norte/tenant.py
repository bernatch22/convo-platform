"""Clínica Norte — demo tenant: appointment rescheduling for a medical clinic in Spain."""

from core.context import Tenant

from .projects.reagendamiento.project import PROJECT

TENANT = Tenant(
    id="clinica-norte",
    name="Clínica Norte",
    region="eu",
    projects={PROJECT.id: PROJECT},
)

"""Template tenant — copy, rename, fill in."""

from core.context import Tenant

from .projects.example.project import PROJECT

TENANT = Tenant(id="example", name="Example Co", projects={PROJECT.id: PROJECT})

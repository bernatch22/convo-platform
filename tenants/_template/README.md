# Tenant template

Copy this folder to `tenants/<your-id>/`, rename, and edit:

- `tenant.py` — id, name, region, the projects it exposes.
- `projects/<project>/project.py` — id, language, voice, `entry_agent()`.
- `projects/<project>/prompts.py` — the prompts of each stage (project data).
- `projects/<project>/agents.py` — one `TenantAgent` subclass per stage.

`core` never imports this package; the registry discovers tenants by folder.

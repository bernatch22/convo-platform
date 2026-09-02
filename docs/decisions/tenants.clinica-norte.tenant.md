# `tenants.clinica-norte.tenant`

The reasoning that used to live in the docstrings of `tenants/clinica-norte/tenant.py`; the code keeps one line per symbol.

## ClinicaNorteTenant.build_adapters

Two of them from ms-3 on: the appointment book and the SMS gateway. The
executor picks whichever one declares the capability a tool asks for, so
adding a system is adding a line here — no stage and no tool changes.

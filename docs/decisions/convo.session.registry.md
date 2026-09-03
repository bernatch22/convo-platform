# `convo.session.registry`

The reasoning that used to live in the docstrings of `convo/session/registry.py`; the code keeps one line per symbol.

## module

`convo/` never imports a tenant statically: the package name is data and the
folders are discovered on disk, so tests keep proving the runtime has no
compile-time dependency on any customer.

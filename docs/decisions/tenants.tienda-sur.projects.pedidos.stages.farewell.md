# `tenants.tienda-sur.projects.pedidos.stages.farewell`

The reasoning that used to live in the docstrings of `tenants/tienda-sur/projects/pedidos/stages/farewell.py`; the code keeps one line per symbol.

## Farewell

Deliberately toolless: everything this stage says it already knows from the
summary OrderDesk left it. A stage that could still touch the order system
would be a second chance to cancel something after the customer has been
told the call is over — which is exactly the bug the three-stage split
exists to prevent.

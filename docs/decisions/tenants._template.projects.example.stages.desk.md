# `tenants._template.projects.example.stages.desk`

The reasoning that used to live in the docstrings of `tenants/_template/projects/example/stages/desk.py`; the code keeps one line per symbol.

## module

The second half is the whole point. Cancelling is irreversible, so it does not
happen because the model decided the customer sounded sure: it happens because
`ConfirmTask` read the booking back, the customer said yes, and that yes minted
a token for exactly this call. The guard refuses `cancel_booking` without it.

TODO(copy): when your irreversible act is more than one write — stop the order
AND text the customer — wrap the steps in `convo.tools.saga.Saga` instead of
calling the tool directly, and the platform will run the `compensation`
declared on the spec (`restore_booking`) if a later step fails.
`tenants/tienda-sur/projects/pedidos/stages/order_desk.py` is that shape.

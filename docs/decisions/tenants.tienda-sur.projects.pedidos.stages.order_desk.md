# `tenants.tienda-sur.projects.pedidos.stages.order_desk`

The reasoning that used to live in the docstrings of `tenants/tienda-sur/projects/pedidos/stages/order_desk.py`; the code keeps one line per symbol.

## module

The whole point of the stage is the second half. Cancelling is irreversible, so
it does not happen because the model decided the customer sounded sure: it
happens because `ConfirmTask` read the order and the amount back, the customer
said yes, and that yes minted a token for exactly this call. The two writes
that make up a cancellation then run as one saga — stop the order, tell the
customer — and if the SMS cannot go out the order is put back exactly as it
was, because in this shop a cancellation the customer has no proof of is not a
cancellation.

## OrderDesk.summary

Two stages read this now and they need different halves of it. Farewell
arrives only after a cancellation and needs it in the words to read out.
TicketDesk arrives from a customer with a problem and needs the ORDER,
so that nobody is asked twice for a number they have already given.

The not-cancelled branch used to answer "todavía no se ha cancelado
nada", which was harmless while Farewell was the only reader and became
a defect the moment it was not: a summary reaches the model as a turn to
ANSWER (a system message added mid-conversation is rewritten as a user
one — see CLAUDE.md), so a customer who had just asked to file a written
complaint was greeted with «el pedido sigue en pie, no se ha cancelado
nada. ¿Qué prefieres hacer?» — every word true, about something nobody
had raised. Measured at 0.4 on the line metric before this was written.

## _cancellation

The compensation is not a technicality: this shop's own rule is that the SMS
is the customer's receipt, so a cancellation nobody could be told about is
undone rather than left standing silently. `restore_order` is declared as
the compensation of `cancel_order` in `project.py`; the saga finds it there.

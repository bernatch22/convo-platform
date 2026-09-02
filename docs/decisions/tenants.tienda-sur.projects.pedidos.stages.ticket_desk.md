# `tenants.tienda-sur.projects.pedidos.stages.ticket_desk`

The reasoning that used to live in the docstrings of `tenants/tienda-sur/projects/pedidos/stages/ticket_desk.py`; the code keeps one line per symbol.

## module

A stage and not a branch, and the argument is ms-18's, run again on this shop.

That argument has two halves. The first is about consent: a stage with two
irreversible doors makes the (write, asking) pair the consent metric watches
ambiguous. It does not apply here — opening an incident is a WRITE, not an
irreversible, so `cancel_order` is still the only door in this project and the
graph is unchanged. The second half is the one that decides it: **does any
contract in the way say the order exists?** Identify's does, in five sentences
and in the shop's own information sheet ("hasta que el pedido no está
localizado no se habla de nada"), and OrderDesk's two tools take no arguments
at all *because* the order is already found. A customer ringing with a ticket
number and no order — the second call in "abre una y consúltala luego" — walks
into that wall, and widening Identify's rule to let them past would weaken the
rule that stops us cancelling somebody else's parcel.

So Identify grows a deliberate second exit, exactly as the clinic's did, and
this stage answers to a different contract: here what is known is the INCIDENT,
and the order is optional context. OrderDesk gets the same exit, because a
customer whose order is already on the table should not have to repeat it.

The prompt cost that a second stage usually carries was paid once and refunded
the same way ms-18 paid it: the shared `<shop_knowledge>` block is byte
identical across the four stages, so the cached prefix is the same object and
no existing golden moved.

## TicketDesk.summary

Two stages read it now. Farewell closes a call that filed one, and OrderDesk
arrives when the customer went back to asking about the parcel — so the note
has to be true for a desk that is NOT going to talk about the incident, which
is why it never asks the next stage to bring it up.

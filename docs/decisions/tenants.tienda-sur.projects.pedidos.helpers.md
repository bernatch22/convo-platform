# `tenants.tienda-sur.projects.pedidos.helpers`

The reasoning that used to live in the docstrings of `tenants/tienda-sur/projects/pedidos/helpers.py`; the code keeps one line per symbol.

## ticket_subject

One line of indirection on purpose: the stage asks the project what a
subject is, and the project asks the system that has to hold it. A shop
that swaps `FakeTickets` for a real helpdesk with a 120-character field
changes one constant and the prompt above it stops promising more.

## opened_line

The number is the whole point of the turn — it is what the customer writes
on the back of an envelope and quotes on the next call — so the instruction
to say it out loud, digit by digit, is here and not left to the prompt: a
tool that returns an identifier nobody repeats has helped no one.

## confirmation_question

A confirmation the model writes is a confirmation the model can soften, and
"¿te lo cancelo entonces?" after three sentences about sizes is not consent
to stop an order. The words are built here from the row the order system
returned, so what the customer agrees to and what the platform cancels are
the same thing by construction.

## cannot_cancel

The refusal and the way out in one string, because they are one thing to say:
a customer who hears "no se puede" and nothing else has been given a problem
instead of an answer. The policy sentence is `messages.RETURN_POLICY`, quoted from the
shop's own information sheet so the two can never drift apart.

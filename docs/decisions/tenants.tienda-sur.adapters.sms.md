# `tenants.tienda-sur.adapters.sms`

The reasoning that used to live in the docstrings of `tenants/tienda-sur/adapters/sms.py`; the code keeps one line per symbol.

## module

The second half of a cancellation is telling the customer in writing, and it is
a write like any other: catalogued, guarded, timed and logged. Keeping it
behind an adapter is what lets the saga treat "send the SMS" as a step that can
fail and be reasoned about, instead of a side effect buried in a stage.

One refusal is deliberate and deterministic: the shop's gateway is a mobile
gateway, so a landline is rejected. It is not decoration — a customer who left
a landline is common, and it is the case where the cancellation goes through
and the confirmation does not, which is exactly what the saga exists for.

A phone number is personal data, so `send_sms` declares `pii_scope={"phone"}`
in the project's catalog and the platform masks it before anything reaches a
log. This fake still holds the number in memory — a test has to be able to
assert who was written to — which is the line a real gateway draws too.

Open source note: replace `_send` with your provider's HTTP call and keep the
capability name and the `{message_id, to}` result. Raise `ValueError` when the
provider refuses; the platform turns it into a sentence the caller hears.

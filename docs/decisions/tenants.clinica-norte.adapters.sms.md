# `tenants.clinica-norte.adapters.sms`

The reasoning that used to live in the docstrings of `tenants/clinica-norte/adapters/sms.py`; the code keeps one line per symbol.

## module

The third step of a rebooking is telling the patient in writing, and it is a
write like any other: catalogued, guarded, timed and logged. Keeping it behind
an adapter is what lets the saga treat "send the SMS" as a step that can fail
and be reasoned about, instead of a side effect buried in a stage.

A phone number is personal data, so `send_sms` declares `pii_scope={"phone"}`
in the project's catalog and the platform masks it before anything reaches a
log. This fake still holds the number in memory — a test has to be able to
assert who was written to — which is exactly the line a real gateway draws too.

Open source note: replace `_send` with your provider's HTTP call and keep the
capability name and the `{message_id, to}` result. Raise `ValueError` when the
provider refuses; the platform turns it into a sentence the caller hears.

## summarise_message

The BODY is deliberately not rendered. It names the patient by design
(`helpers.sms_text`), and while the mask would blank the name, a summary
whose value depends on the mask having seen that exact spelling is a
summary waiting to leak. The id and the number are what an operator needs
to answer "did the patient get their text?".

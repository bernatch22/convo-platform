# `tenants.clinica-norte.projects.reagendamiento.stages.update_contact`

The reasoning that used to live in the docstrings of `tenants/clinica-norte/projects/reagendamiento/stages/update_contact.py`; the code keeps one line per symbol.

## module

The clinic's third irreversible door and the first that is not about an hour.
Two things make it its own stage rather than a branch of anything:

- it is reachable only from an identification, and it is the one errand where
  the identification IS the safeguard. A caller nobody found on the book cannot
  change anybody's data, and that refusal lives one stage earlier — in
  `Identify.start_contact_update`, which hands this stage a patient or hands the
  model a sentence and no handoff.
- the number on file never gets here whole. `Identify.summary()` reduces it to
  its last three digits before the handoff, so the stage that reads a value back
  to the caller physically cannot read out more of it than the caller is
  entitled to hear. A prompt paragraph says the same thing; this is the half
  that holds when the prompt does not.

The write itself is the shape the two booking stages already established:
the model calls a tool that asks, `ConfirmTask` reads the platform's own
sentence back and waits for a yes, and only then does `update_contact` reach the
clinic's records with a token minted for exactly those arguments. There is no
saga, and that absence is the point — one step, nothing to compensate, and
nothing anybody could compensate it with: the number it replaced is not kept.

## _contact_args

The appointment id is the caller's identity here, not a detail of the write:
it is what `Identify` put on the context when it found them on the book, and
an empty one means nobody was found. The adapter refuses it too
(`patients.update_phone`), which is the belt to this braces — a stage can be
rewritten, and the record must still refuse a stranger.

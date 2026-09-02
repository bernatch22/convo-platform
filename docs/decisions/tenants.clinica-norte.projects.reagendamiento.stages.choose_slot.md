# `tenants.clinica-norte.projects.reagendamiento.stages.choose_slot`

The reasoning that used to live in the docstrings of `tenants/clinica-norte/projects/reagendamiento/stages/choose_slot.py`; the code keeps one line per symbol.

## module

The whole point of the stage is the last step. Booking is irreversible, so it
does not happen because the model decided the conversation had gone well: it
happens because `ConfirmTask` read the hour back to the caller, the caller said
yes, and that yes minted a token for exactly this call. The three writes that
make up a rebooking then run as one saga — release the old hour, take the new
one, send the SMS — and any failure puts the old appointment back.

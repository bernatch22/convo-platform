# `convo.testing.metrics.grounding.extract`

The reasoning that used to live in the docstrings of `convo/testing/metrics/grounding/extract.py`; the code keeps one line per symbol.

## module

Half of `convo.testing.metrics.grounding` — the half that reads what the AGENT said. An
`Extractor` is a regex plus the keys a match has to be found under, so a project
declares its own vocabulary (professional titles for a clinic, order numbers and
carriers for a shop) and inherits the three every project needs: clock hours,
prices and phone numbers.

`stated_data` runs those extractors over the assistant turns and only over
those: "las citas se pueden cambiar" is a policy, "90 euros" is a number
somebody can be wrong about.

Nothing here knows a language. The Spanish spoken hour, the `Dra.` title and the
`TS-1043` order number are extractors their own projects declare.

## vocabulary

Pass `against=CALL` for a claim the knowledge block must not be allowed to
ground: the sheet lists every carrier the shop uses, so only the call itself
can say which one has THIS parcel.

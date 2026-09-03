# `tenants.clinica-norte.projects.reagendamiento.stages.cancel_or_confirm`

The reasoning that used to live in the docstrings of `tenants/clinica-norte/projects/reagendamiento/stages/cancel_or_confirm.py`; the code keeps one line per symbol.

## module

**Why a stage and not a branch of ChooseSlot.** Ms-18 wrote the rule down when
`create_appointment` was the second irreversible verb: the consent policy watches
an (irreversible, asking) PAIR, and a stage holding two irreversible doors makes
that pair ambiguous — which of them did the caller's yes belong to? ChooseSlot
already owns `book_slot`, so a cancel bolted onto it would have been the second.
The other half of the argument is the contract: ChooseSlot's prompt says "the
appointment exists AND is being moved" in half a dozen paragraphs about reading
an agenda, and a cancellation reads no agenda at all.

**Why ONE stage for two verbs and not two.** The same rule, read honestly, says
nothing against it: only `cancel_appointment` is irreversible here, so the pair
stays unambiguous. And the conversation genuinely is one conversation — the cita
is looked up, read back and agreed to identically for both — so two stages would
have meant two copies of the read-back drifting apart, which is precisely what
the `prompts/_partials/` partials exists to prevent. What parts is the last sentence: an
hour released, or an hour written down as spoken for.

**Why the cita is looked up here rather than inherited.** `Identify.summary()`
does hand this stage the cita, and the stage still calls `find_my_appointment`
before it says a word. A cita recited off a note is a claim with no source in the
call — `grounded_facts_dag` escalates the hour to a judge and is right to — and,
less abstractly, it may have been moved this morning by somebody else. The
lookup is also the whole of the leak defence: it takes no name, only the identity
the previous stage put on the context, so a caller asking about their husband's
cita is not refused by a paragraph, they are refused by a stage that has no way
to ask.

## _lookup

Keyed on what `Identify` already established — the phone it found them by,
falling back to the name — and never on anything the model passes, which is
what makes "one patient per call" a property of the code rather than a
paragraph a model can be talked out of. A context with neither is an
unidentified caller and answers None, so the stage refuses instead of
reading somebody else's cita out.

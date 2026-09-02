# `convo.testing.metrics.grounding`

The reasoning that used to live in the docstrings of `convo/testing/metrics/grounding/__init__.py`; the code keeps one line per symbol.

## module

The judge that used to answer "did the agent invent this?" could not see the
evidence, so it guessed, and it guessed differently on Tuesday than on
Wednesday: the clinic's price golden flipped between 0.0 and 0.9 across runs of
the same prompt. The fix is not a better-worded criterion. It is to stop asking
a model a question that code can answer.

This package is the half of that answer that belongs to no business, in two
files a reader can hold in their head at once:

- `extract.py` — the patterns and the normalisers: what a project can be wrong
  about (`Extractor`, `Datum`, `stated_data`), matched after lowercasing,
  stripping accents and reading hours as `HH:MM`.
- `evidence.py` — what the call produced that could ground a claim (`Evidence`,
  `evidence_of`) and what is left over when nothing does (`unsupported`).

Both halves are re-exported here, so `from core.testing import grounding` and
every `grounding.<name>` a project writes keep working unchanged.

Open source note: nothing here knows a language. The Spanish spoken hour, the
`Dra.` title and the `TS-1043` order number are extractors their own projects
declare; what is reusable is extract → match → escalate the remainder.

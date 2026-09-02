# `convo.testing.metrics.leakage`

The reasoning that used to live in the docstrings of `convo/testing/metrics/leakage.py`; the code keeps one line per symbol.

## module

One worker serves every tenant, so the only thing keeping Clínica Norte's
doctors out of Tienda Sur's answers is that each session is built from its own
project data. That is an architectural claim, and a claim is worth a metric:
ask the shop for a traumatology appointment, ask the clinic where a parcel is,
and read what comes back.

Two questions, in the order of what they cost:

1. **Did the reply name anything that belongs to the other business?** A word
   scan, not a judge — the other tenant's proper nouns are a list (its brand,
   its site, its doctors, its carriers, its phone), and a reply containing one
   of them is a 0.0 whatever the sentence around it was doing. This is the node
   that can actually catch a leak, and it costs nothing.
2. **Did it stay in its own business and redirect politely?** The genuine
   language question, and the only judge call: an agent that invents a booking
   system it does not have leaks nothing by name and is still wrong.

The scan is `core.testing.register.slips`, the same whole-word pass over
flattened text the register check uses, so «norte» never trips on «Clínica
Norte» and an accent or a full stop in a doctor's name never hides a leak.

Open source note: the graph is reusable as it stands and the word lists are
not. Any platform running several businesses on one runtime can copy this file;
what each tenant has to write is the short list of nouns that only ever belong
to somebody else.

## mentions

Terms are flattened before the scan, so a project writes its neighbour's
nouns the way they are spelled — «Clínica Norte», «Dr. Alberto Navarro» —
and still matches what a model actually says.

## leakage_graph

`other_terms` is the neighbour's proper nouns; `criteria` is the one
sentence this project wants a judge to answer about a question it cannot
serve. Both are project data (`tenants/<id>/projects/<p>/evals/dag.py`) —
the graph knows nothing about either business.

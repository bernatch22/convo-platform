# `tenants.clinica-norte.projects.reagendamiento.evals.metrics`

The reasoning that used to live in the docstrings of `tenants/clinica-norte/projects/reagendamiento/evals/metrics.py`; the code keeps one line per symbol.

## module

One small explicit list, in the project folder next to its goldens: what counts
as a good reply for a clinic's reception ("usted", two or three sentences, never
invents an hour) is not what counts for a shop's returns desk, and a threshold
is a business decision, not a platform default. `tests/evals/` and
`core.testing.report` both build their metrics from here, so the CI gate and the
HTML a reviewer reads score the same runs by the same rules.

Every factory returns a fresh instance: a DeepEval metric keeps the score,
reason and cost of the last case it measured, so sharing one across a
parametrized suite would have the tests overwrite each other's results.

## reception_line

This metric used to own the invention rule too, and it could not hold it.
A GEval turns its criteria into evaluation steps, and a step keeps only the
clause it grew from, so "an hour needs a tool behind it" survived its own
exception and failed the price answer for quoting 90 euros with nothing
called — intermittently, 0.0 on one run and 0.9 on the next, because a
judge with no evidence in front of it is guessing. Rewriting the sentence
bought a week each time. The rule now lives in `grounded_facts_dag`, where
code does the matching and the judge is only ever handed a claim and the
document that does or does not contain it. What is left here is tone,
register, length and remit — the things a judge is actually good at.

Ms-20 found the boundary of what this metric can be pointed at, and it is a
fact about the platform rather than about the criteria. A golden that judged
a CONFIRMATION turn scored 0.2 on both models with an impeccable reply: the
sentence the judge was reading was `ConfirmTask`'s own — rendered by the
platform, spoken verbatim — and `actual_output` merges the two voices, so
the judge attributed it to the model, mined the tool docstring for a
workflow and failed the turn for "asking permission before the tool
executes". Three rewordings did not move it, because nothing was wrong.
A turn the platform speaks in does not belong in this suite; what it does
belongs to `tests/test_stages.py`, which counts the calls, and to the
consent DAG, which reads the log. That golden was withdrawn, not softened.

It grew a third half in the same milestone, for the same reason and one card
later: `transfer_to_human` made «páseme con una persona» a legitimate thing
to ask a clinic's reception, and a criterion that lists what a business does
is a scope test. The verb and the clause landed in the same commit, which is
the only way this metric survives a business that grows.

The remit clause grew a second half in ms-20 and it was a metric defect, not
a model one. Asked «dígamelo entero», the agent refused to read a phone
number out and offered its last three digits — the whole point of that
errand — and the judge scored it 0.3 while writing, in its own reason, "the
response itself is well-executed". A criterion that lists what a business
does is a scope test, and a business that grew a verb has to grow the list
in the same commit or the metric starts failing correct calls.

The second half of ms-20 found the LAST thing this metric was silently
grading, and it is the same defect one layer over: the tool calls. On «quería
anular la cita que tengo» — a caller who has not said their name — gpt-5.4-mini
called `start_cancellation` with an empty name, and the judge scored an
otherwise textbook reply 0.3 for "a significant protocol violation", quoting
the tool's own docstring back at it. The model IS wrong there and the golden
is right; what is wrong is which metric said so. `tools_called` is in
`evaluation_params` so the judge can SEE what a turn is answering — several
goldens describe a turn that must not consult the agenda — and a judge shown
a tool call grades it unless told twice not to. "Did the right tool run with
the right arguments" is `tool_correctness` and `argument_correctness`, both
deterministic or evidence-gated and neither of them guessing. The criterion
now says so in words, exactly as it already did for facts.

Every either/or is still spelled out as "one alone is enough". Written as a
plain "a question or a next step" the judge read it as a demand for a
SPECIFIC next step and scored an ideal de-escalation 0.5 for ending on
"¿qué necesita?". A judge parses a disjunction as a checklist unless told
twice, and that is a property of judges, not of this criterion. Ms-5 found
the same sentence still open at the other end: told only that both were
"never required", the judge read an exclusive or and scored 0.6 for a reply
that gave the price AND asked for the name. It now says both halves, in the
same words the shop's criteria uses.

The tools called stay in the evaluation params: several goldens describe a
turn that must not consult the agenda, and a judge that cannot see whether
it did has to guess at that too.

## no_false_success

The one judgement in this project that had to leave the unit ring. It was a
`.judge(...)` inside `tests/test_stages.py`, and across two consecutive full
runs of `pytest -m unit` it failed once and passed once on the same code: a
gate that flips is not a gate. What it was really doing there was asking a
model for an opinion in a suite whose whole value is that it asks for none.

The deterministic half stayed where it was and lost nothing —
`test_a_refused_hour_leaves_the_old_appointment_standing` still pins the
three calls, the appointment that is still booked and the SMS that never
went out. This scores the sentence, and it scores it with the evidence in
front of the judge: the turn carries the platform's own writes, `book_slot`
among them with "refused: the customer's system rejected it and nothing was
written" as its output, so the judge is never guessing at what happened.

`threshold=0.8` and not the 0.7 the line metrics use: telling a patient a
change went through when it did not is the kind of defect a demo cannot
survive, and there is very little room between "said it plainly" and "let
them believe it worked".

## tool_correctness

Deterministic and free: with no `available_tools` given, DeepEval compares
the names called against the names expected and never asks a judge. Both
directions are graded — a golden that expects nothing and got nothing
scores 1.0, and one that expects nothing and got a call scores 0.0 — which
is what makes the three "must not call" goldens worth running.

Neither `should_exact_match` nor `should_consider_ordering` is set. Calling
the agenda twice for one question (the patient named a day and a specialty)
is not a defect worth failing a build over; calling it for a price question
is, and the default scoring already says so.

## argument_correctness

Judged, not compared: the tool takes the day in the caller's own words, so
"el jueves", "este jueves" and "2026-09-03" are all correct for the same
question and no literal expected value could accept the three. The suite
pins the resolved date separately, with `dates.resolve`; this metric is
what catches a specialty invented or a day quietly swapped.

It only works if the call carries the tool's description — the bridge puts
it there. Without it the judge scored `date="el jueves"` 0.0, reasoning
that the tool "requires YYYY-MM-DD": a contract it made up, and the exact
opposite of what the docstring the model reads asks for.

## never_book_before_yes

The one metric in this project with no partial credit, which is why it is a
DAG and not a GEval: `threshold=1.0` and the graph only ever scores 1.0 or
0.0, so "mostly asked for consent" is a failure and reads like one. The
graph, the wording of each node and why the metric watches `book_slot`
rather than `book_appointment` are all in `dag.py`.

`include_reason=False` for the same reason as `grounded_facts_dag`: the two
first nodes are computed, so a call in which nothing was booked costs zero
model calls — and DeepEval's generated summary would be the only one left.
Each node writes its own line into `verbose_logs` instead.

## never_create_before_yes

The same graph as `never_book_before_yes` with the other pair of tool names,
and the same 1.0-or-0.0: a first cita written without a yes is a hueco another
patient could not use and a stranger's name on the clinic's book, which has no
partial credit either.

It costs a judge call only when `create_appointment` actually ran. A caller
who backs out at the confirmation ends the graph at its first, computed node
— which is why the backing-out golden of this project is free to run on every
model and in every nightly.

## never_change_contact_before_yes

The third door, ms-20, and the one where the damage is silent: a wrong
number on a record produces no error anywhere — the clinic simply stops
reaching that patient, and nobody finds out until somebody misses an
appointment. So it has no partial credit either, and it is watched by name
for the same reason the other two are: `request_contact_change` is the model
asking, `update_contact` is the record changing.

## never_cancel_before_yes

The fourth door, ms-20, and the one whose damage is instant and public: the
hour goes back into `find_availability` the moment the write lands, so by the
time anybody notices, another patient may be holding it. There is no undo to
fall back on and therefore no partial credit either.

It is watched by name like the other three — `request_cancellation` is the
model asking, `cancel_appointment` is the book losing the cita — and it costs
a judge call only when the cancellation actually ran, which is what makes the
backing-out golden free to run on every model.

## grounded_facts_dag

The evidence-gated pattern, and the reason this is a DAG and not a GEval:
code extracts the claims and matches them against the clinic's sheet, what
the caller said and what the tools returned, and only what survives that is
shown to a judge — one binary question, with the evidence attached. A reply
whose every fact matches costs zero judge calls, which is why it can run on
every golden of the suite instead of on the two somebody remembered.

`include_reason=False` on purpose: DeepEval's reason is a generated summary,
and it would be the only model call in a metric built to have none. Every
node writes its own one-line reason into `verbose_logs` instead — run the
suite with `-v` (or `verbose_mode=True`) to read which claim was left over.

## keeps_the_register

No judge at all: the graph is one deterministic node over a list of tú-forms
(`dag.TU_FORMS`). It exists because a GEval asked about tone scored an
otherwise good reply 0.8 and moved on, while for a clinic a single "¿cuál te
viene mejor?" in a call that has been usted throughout sounds like another
person picking up the phone. A rule a word list can decide is not a judge's
to weigh.

## no_leakage

The shop next door runs on the same worker, the same registry and the same
session code; the only thing that keeps its carriers and its order numbers
out of this call is that the context was built from this project's data.
That is a claim about the runtime, so it is measured and not asserted in a
docstring. Word list and criterion in `dag.py`, graph in
`core.testing.leakage`.

`threshold=1.0`: naming another business, or pretending to track anything,
has no partial credit.

## consent_policy

`convo sessions eval <id>` scores a stored session of ANY project, so the
name it reads cannot be a clinic word: what a shop does irreversibly is
cancel an order, not book an hour. Each project answers to `consent_policy`
and calls its own metric whatever its business calls it.

This clinic has FOUR irreversible doors since ms-20 — moving a cita,
creating one, changing the number it reaches a patient on, and cancelling
the cita outright — and a stored session does not announce which it went
through, so the graph here watches all of them. Returning
`never_book_before_yes()` would have scored every new-booking session 1.0
without reading a thing: its first node asks whether `book_slot` ran, and in
that call it never does.

## line_metric

The same trick as `consent_policy`, for the same reason: one report scores
every project with one set of factories, and what a reply has to SOUND like
is called something different in every business — a clinic has a reception
line, a shop has an order desk. Each project answers to `line_metric` and
calls its own metric whatever its business calls it.

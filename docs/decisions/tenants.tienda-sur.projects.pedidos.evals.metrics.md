# `tenants.tienda-sur.projects.pedidos.evals.metrics`

The reasoning that used to live in the docstrings of `tenants/tienda-sur/projects/pedidos/evals/metrics.py`; the code keeps one line per symbol.

## module

What counts as a good reply for a shop is not what counts for a clinic: three
short sentences of tuteo that end on "¿te ayudo con algo más?" would be a
register failure in Clínica Norte and are the house style here. The thresholds
are a business decision too, so they live next to the goldens and not in `convo/`.

`tests/evals/` and `convo.testing.reports.report` both build their metrics from here, so
the CI gate and the HTML a reviewer reads score the same runs by the same rules.

Every factory returns a fresh instance: a DeepEval metric keeps the score,
reason and cost of the last case it measured, so sharing one across a
parametrized suite would have the tests overwrite each other's results.

## order_desk_line

The clinic learned this split the hard way: a GEval that also owned "did it
invent this?" flipped the same correct answer between 0.0 and 0.9 across
runs, because a judge with no evidence in front of it is guessing. Facts
live in `grounded_facts_dag`, register lives in `keeps_the_register`, and
what is left here is tone, length and remit — the things a judge is good at.

Every either/or is spelled out twice: "one alone is enough" AND "doing both
is also correct". A judge reads a plain disjunction as a checklist and
marks an ideal short answer down for not also naming a next step; told only
that both are "never required", it read the sentence as an exclusive or and
scored 0.6 for a reply that helpfully did both. A disjunction has to be
closed from both ends or a judge will pick one.

The "did the right THING" clause is the other half, and ms-5's evals card
paid for it: on the decline golden — «no, espera, mejor lo dejo», a customer
KEEPING their order — the judge read the Spanish backwards, decided they had
asked to cancel, and scored a correct reply 0.2 for "contradicting the
customer's intent". A tone judge allowed to grade the DECISION will grade
it, and one that has misread a line then fails the whole reply for it.
Consent is `never_cancel_before_yes` and tool choice is `tool_correctness`;
this metric is now told in words that neither is its business.

The remit clause grew in ms-20 with the clinic's, and for the same reason
read the other way round: the platform's `transfer_to_human` exists, this
shop names no `transfer_number`, and so a customer asking for a person gets
an honest "you are already speaking to support" and the shop's other
channels. A criterion that lists what a business does has to say that is
correct, or it fails the very answer the missing number is supposed to
produce.

## tool_correctness

Deterministic and free: with no `available_tools` given, DeepEval compares
the names called against the names expected and never asks a judge. Both
directions are graded — a golden that expects nothing and got nothing scores
1.0, and one that expects nothing and got a call scores 0.0 — which is what
makes the three "must not call" goldens (returns policy, weather, complaint)
worth running.

There is no ArgumentCorrectness in this project, and that is not an
oversight. The two tools of the order desk take no arguments at all (the
order is already identified); `identify_order` does, and is pinned by
`tests/test_tienda_stages.py` against the order book, where there is exactly
one right answer and a judge would only add variance to it. `open_ticket`
is the third case and the reason the rule is worth writing down: its
argument is free text a customer dictated, so there is no right answer to
compare against — only a rule about what must NOT be in it, which the
goldens judge as words and `tests/test_tienda_tickets.py` pins as storage
(what the helpdesk keeps is the caller's own sentence, trimmed and never
rewritten).

## never_cancel_before_yes

The one metric in this project with no partial credit, which is why it is a
DAG and not a GEval: `threshold=1.0` and the graph only ever scores 1.0 or
0.0, so "mostly asked for consent" is a failure and reads like one. The
graph is `convo.testing.metrics.dag.consent_graph`; what this project supplies is the
two tool names and the wording of "was that a yes".

`include_reason=False` for the same reason as `grounded_facts_dag`: the two
first nodes are computed, so a call in which nothing was cancelled costs
zero model calls — and DeepEval's generated summary would be the only one
left. Each node writes its own line into `verbose_logs` instead.

## grounded_facts_dag

Code extracts the claims and matches them against the shop's sheet, what the
customer said and what the order system returned; only what survives that is
shown to a judge, as one binary question with the evidence attached. A reply
whose every fact matches costs zero judge calls, which is why it can run on
every golden of the suite instead of on the two somebody remembered.

`include_reason=False` on purpose: DeepEval's reason is a generated summary,
and it would be the only model call in a metric built to have none. Every
node writes its own one-line reason into `verbose_logs` instead.

## keeps_the_register

No judge at all: one deterministic node over a list of usted-forms
(`dag.USTED_FORMS`). Two tenants with opposite registers are the cheapest
possible proof that register is project data — the clinic runs the same
metric with the tú-forms and the same graph builder.

## no_leakage

One worker serves both businesses, so "a shop never answers as a clinic" is
an architectural claim about `convo/` and not a property of this prompt —
which is exactly why it is worth one golden and one metric. The word list of
the other tenant's proper nouns and the redirect criterion are `dag.py`; the
graph is `convo.testing.metrics.leakage`, shared with the clinic's own `no_leakage`.

`threshold=1.0`: naming another business, or playing along with a request it
cannot serve, has no partial credit.

## consent_policy

`convo sessions eval <id>` scores a stored session of ANY project, so the
name it reads cannot be a shop word either. Each project answers to
`consent_policy` and calls its own metric whatever its business calls it.

## line_metric

The same trick as `consent_policy`, for the same reason: one report scores
every project with one set of factories, and what a reply has to SOUND like
is called something different in every business — a clinic has a reception
line, a shop has an order desk. Each project answers to `line_metric` and
calls its own metric whatever its business calls it.

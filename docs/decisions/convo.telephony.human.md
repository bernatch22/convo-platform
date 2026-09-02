# `convo.telephony.human`

The reasoning that used to live in the docstrings of `convo/telephony/human.py`; the code keeps one line per symbol.

## module

`core.security.control` already lets a supervisor move a call from the desk.
This is the other half the spec asks for: the agent itself deciding «le paso
con un compañero» because the caller asked for one, or because what they need
is not something reception can do.

Three things live here and nothing else, so that the console, the executor and
the prompt all read one declaration:

- **the number is project data.** `Project.transfer_number` is where a call
  goes, in E.164, and it is overridable from the console like the voice and the
  greeting — a business changes the phone its reception overflows to far more
  often than it redeploys.
- **a tool that cannot work is not offered.** No number means the model never
  sees `transfer_to_human` in its tool list, and the console greys the verb out
  with the sentence a PUT would be refused with. That is the same
  `unavailable_reasons` idiom `core.pipeline` uses for a provider whose key
  this box does not carry, and it is the opposite of a runtime surprise: a
  transfer that fails in the middle of a call costs a caller their patience,
  and one that was never possible costs them nothing.
- **the words.** The paragraph that teaches a stage to announce the handover
  before it happens, and the three sentences the tool answers with.

Framework-free on purpose: it imports `core.telephony.transfer` for the E.164
rule and nothing else, so `core.pipeline` — which every console read goes
through — does not drag the agent runtime in behind it. The half that touches
livekit is `core.adapters.human` (the run) and `core.agents.human` (the door
the model knocks on).

## refusal

Empty is not a refusal: it is how the console CLEARS the number, and
clearing it takes the verb away from the model rather than leaving it a tool
that fails. Everything else has to be a number `TransferSIPParticipant` can
dial — E.164, `+` and digits — because a REFER carries a `tel:` URI and a
name, an extension or a spaced-out number reaches no carrier at all.

## view

`unavailable_reasons` is keyed by the TOOL name and carries the sentence
verbatim, exactly like `stt_view` and `llm_view`: the console greys the verb
and repeats the server's own words instead of keeping a second copy of the
rule.

## protocol

Three answers, and the third is the one that was measured. A project that
declares the spec and names a number is taught the verb; one that declares
it and names nobody is taught that there IS nobody, which is a fact about
the deployment and not a rule about a tool it does not have; and a project
that never declared it is told nothing at all, because core does not invent
policy for a business that has not asked the question.

The middle case exists because of one shop golden on 2026-08-31. Asked
«pásame con una persona», tienda-sur — no number, no tool, no paragraph —
answered «Entiendo, ahora mismo te paso», which is a promise nothing in the
platform can keep: the caller waits for a voice that never arrives. Silence
is not honesty. Naming the TOOL there would be the other mistake — a rule
about a verb the model does not have is the surest way to have it reach for
one — so the paragraph names the situation instead.

Spanish, like `core.security.protocol.SUPERVISOR_PROTOCOL` and for the same
reason: both demo tenants are. A project in another language writes its own
paragraph and appends that instead.

**What this paragraph costs, measured (2026-09-01, 154 runs of
`test_a_caller_with_no_cita_is_handed_over_to_the_stage_that_creates_one`,
claude-haiku-4-5).** The test went flaky when this card landed and the
paragraph was the prime suspect — its wording, and its position in the last,
most-recent slot of the prompt. Both were innocent:

| cell                                          | pass/valid | fail |
|-----------------------------------------------|-----------:|-----:|
| card reverted — no tool, no paragraph          |      38/40 |   5% |
| v1: nine sentences of prohibitions, last slot  |      15/20 |  25% |
| v2: tool named in the clause, moved off last   |      31/40 |  22% |
| **no paragraph at all, tool still offered**    |      16/20 |  20% |
| v3: this one — short, positive, docstring-led  |      28/34 |  18% |

Every cell with the TOOL is 18-25% and they are indistinguishable from each
other (v1 vs v2 p=1.0, v1 vs v3 p=0.73, paragraph vs no paragraph p=1.0).
Pooled, tool-present is 90/114 against the floor's 38/40 — **p=0.025**. The
cost is the TOOL on the stage's surface, not any sentence in the prompt:
`Identify` now chooses among one more verb, and it is the published effect
that every tool an agent carries is one more distraction it must ignore.

That is a real price for a real feature and it is written down rather than
softened. The verb has to be reachable in the first ten seconds of a call —
that is when somebody asks for a person — so taking it off the entry stage
would cost more than it saves. If it has to be bought back, the lead is
`Identify`'s own instructions, not this paragraph.

## said

The mode decides the success sentence, because the two ends differently:
a cold REFER takes the caller AWAY, a warm bridge brings the colleague IN.

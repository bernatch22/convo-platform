# `convo.testing.reports.ring2_goldens`

The reasoning that used to live in the docstrings of `convo/testing/reports/ring2_goldens.py`; the code keeps one line per symbol.

## module

Ring 1's goldens are one turn each, because a turn is what a headless run
produces. A ring-2 golden is a whole CALL — a persona, an objective, the lines
that caller says out loud, and the policies that must survive the call being
held over a real microphone. It is JSON in the project's own `evals/` folder,
next to the ring-1 goldens, for the same reason those are: what a business
wants tested is the business's to write.

**The two cases, and why there are two.** A synthetic caller hears everything
that was SAID and nothing that was DONE: no track carries a tool call. So a
finished call is scored on two objects, and which one a policy reads is not a
preference:

  the WIRE case  the transcript both sides produced over WebRTC — what Soniox
                 made of the caller and what the agent actually spoke. Register
                 and cross-tenant leakage are facts about words out loud, and
                 this is the only place they are true. It carries the audio and
                 the latency of every turn, and it is `flaky=True`, because a
                 packet loss is not a regression.
  the LOG case   the same call rebuilt from its append-only event log, through
                 `convo.testing.replay` — ring 3's reader, pointed at a session
                 that ended a second ago. Consent is a fact about what the
                 platform DID (`book_slot` ran; `cancel_order` ran), and only
                 the log has it.

Grounding is still not offered as a ring-2 policy; `docs/decisions/convo.testing.replay.md`
says what the log does and does not carry of a tool result. Asked here it
would fail every correct call, which is how a metric stops being run.

Open source note: nothing below is a clinic or a shop. `POLICIES` names the three
factories a project's `evals/metrics.py` is expected to expose, and the rest is
JSON.

## LiveRun.out_of_character

Three questions, in the order they stop being worth asking. Did the
agent answer every line? Did the impatient one actually cut in — a
barge-in test where nobody was interrupted has tested politeness. Did
the code-switcher come back in both languages, which is the whole of
the `language_hints` evidence.

## LiveRun.languages_heard

Read off the CALLER's turns, which carry what Soniox heard and not what
we meant to say — the only place in the suite where `language_hints`
leaves a mark. A caller who says "hola, hi, I need to change mi cita"
and comes back as Spanish-only did not prove the hints are set; it
proved they are not.

## golden

Every refusal here happens before a single euro of TTS is spent, which is
the point of doing it at load time: a typo in a policy name is worth
finding now and not after four minutes of talking.

## metrics_by_source

Grouped and not listed, because `assert_test` scores one case against many
metrics: a golden asking for consent and register is two calls to it, not
three, and the report reads as two runs of one call rather than three.

## logged_case

The harness is a client, not the control plane: it reads `/sessions/<id>`
and hands the events to ring 3's own reader, so a nightly run against the
box needs no database on the machine it runs from. A session the door
cannot serve is None — the wire half of the run is still worth scoring.

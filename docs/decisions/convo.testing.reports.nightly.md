# `convo.testing.reports.nightly`

The reasoning that used to live in the docstrings of `convo/testing/reports/nightly.py`; the code keeps one line per symbol.

## module

`deepeval test run` is what a person types; this is what a machine runs at
04:00 with nobody watching, and the difference is entirely about money and
evidence.

  **The budget is counted before a euro is spent.** Every ring-2 golden is one
  live call — ElevenLabs speaking, Soniox listening, Haiku answering — so the
  number of goldens across the fleet IS the bill. `affordable` adds them up
  first and takes whole suites while they fit; a suite that would push the
  night past `BUDGET` is skipped, named in the log and on the page, and makes
  the run exit red. It is never trimmed to fit: half a suite scores half a
  policy, which is worse than not running it.

  **Nothing runs blind and nothing runs forever.** Every line the child writes
  goes into `tmp/evals/<date>.log`, and the whole night is killed at
  `DEADLINE_S` — the deadline is over the RUN, not over one suite, because what
  must be bounded is the box's spend and not any single call.

  **Red means red, and pytest's exit code is not what says so.** A ring-2 wire
  case is `flaky=True` by design, so `deepeval test run` exits 0 on a call
  whose register broke. `status_of` reads the scores instead; the argument is
  written out there, and it was paid for on the box.

What a night leaves behind — the page, the index line and the row on the
console — is `convo.testing.reports.nightly_report`.

    uv run python -m convo.testing.reports.nightly                    # the whole fleet
    uv run python -m convo.testing.reports.nightly --only tienda-sur/pedidos --budget 2
    uv run python -m convo.testing.reports.nightly --dry-run          # what it would spend

`CONVO_API` is the control plane the suites call to mint their rooms; on the
box it is the local api, so the calls land on the DEPLOYED fleet. `--console`
exists because the box that runs a night and the console that keeps it need not
be one process; it defaults to `--api`, which is the normal case.

Open source note: nothing here knows a tenant. It globs for a conventional
suite file under `tenants/`, reads a JSON count next to it, and runs pytest —
point it at any repo laid out that way.

## discover

A project declares its ring 2 by having the file, not by naming it in a
registry: the nightly is a fleet-wide sweep, so "every project that has
one" is the honest selection and a new project needs no wiring here.

## affordable

Taken in order until the next one would not fit, and then still offered to
every later suite — a cheap one behind an expensive one is not punished for
its neighbour. What is skipped is returned, never dropped: the caller says
so and the run goes red, because a fleet that outgrew its budget is a
decision for a person and not a number to quietly raise.

## status_of

This is the whole of "red means red", and it is not paranoia: it is the one
thing this card measured on the box. A ring-2 wire case is `flaky=True` on
purpose (`ring2_goldens.LiveRun.wire` — a dropped packet is not a
regression), and DeepEval honours that by refusing to let a flaky metric
decide a case's pass/fail. So `deepeval test run` exits **0** on a call
where the register broke, and a nightly that trusted the exit code would
report a green night over a red metric. Proved on convo-box on 2026-08-31:
a tuteo greeting scored `Keeps the register` 0.00 and pytest still passed.

Trusting the scores instead means a genuinely flaky call can turn a night
red. That is the trade this run makes on purpose: nobody is watching at
04:00, and a red somebody has to look at costs a minute, while a green over
a broken policy costs whatever the policy was protecting. The counts and
the transcript are both on the page, so telling one from the other is one
click.

## scored

Reading the file DeepEval wrote — rather than parsing the table it printed
— is what keeps this page and `deepeval test run` from ever disagreeing
about a score. A suite that crashed before it scored anything wrote no
file, and that is not an error here: the status already says it failed.

## _command

Colour off: the only readers of this output are a log file and a journal,
and escape codes in both are noise somebody has to remember to pipe through.

## _child_env

The provider keys are already here — systemd hands them over from the box's
`.env`, and a laptop run loaded the same file — so nothing this function
reads or writes could put one on disk.

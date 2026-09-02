"""`convo evals report|nightly|record|golden …`: the eval rings a person runs by hand."""

USAGE = """usage: convo evals <verb> [args]

  report  <tenant> <project> [--model M]   ring 1 on one project, HTML under tmp/reports
  nightly [--only t/p] [--budget EUR]      ring 2 against the deployed fleet, on a budget
  record  <tenant> <project>               one recorded call through the real pipeline
  golden  [args]                           regenerate the TTS goldens the voice ring replays
"""


def main(argv: list[str]) -> int:
    """Dispatch to the module that owns each verb; the modules keep their own argparse."""
    if not argv:
        print(USAGE)
        return 2
    verb, rest = argv[0], argv[1:]
    if verb == "report":
        from convo.testing.reports import report

        report.main(rest)
        return 0
    if verb == "nightly":
        from convo.testing.reports import nightly

        return nightly.main(rest)
    if verb == "record":
        from convo.testing.reports import record

        return record.main(rest)
    if verb == "golden":
        from convo.testing.callers import tts_golden

        return tts_golden.main(rest)
    print(USAGE)
    return 2

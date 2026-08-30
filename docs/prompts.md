# Prompts — git is the seed, the database is the override, the version is in the log

Every stage prompt opens with the project's stable knowledge block (the clinic
sheet, the shop policy) — first, byte for byte, because Claude Haiku 4.5 only
caches a prefix of 4,096+ tokens and only while it is identical. Where that
block comes from is a two-layer rule:

1. **The seed lives in git.** `Project.knowledge_seed` is the module constant
   the tenant registers (`knowledge.CLINIC`); every deploy carries it and every
   test renders it.
2. **A pinned row overrides it without a deploy.** `python -m convo versions pin
   <tenant> <project> <version> [<file>]` writes `project_versions`; the router
   reads the pin when a session starts, puts the version into the context and
   into the session's first event (`session.start.project_version`), and
   `Project.knowledge(tc)` returns the override instead of the seed.

What never goes in the block: dates, ids, anything per request — they would
throw the cache away. What a version pin is for: a price change, an opening
hours change, a new doctor — the kind of edit a business makes on a Tuesday
without waiting for the next release.

Read a session's version with `python -m convo sessions show <id>` (seq 1).

# Screenshots — the deck's evidence

A screenshot in this deck is **evidence**, not decoration: it is the console
showing a number the slide claims. If the slide would read the same with the
image removed, the image does not belong on it.

## The convention

- **Where they come from:** the deployed console, `https://lk.bernardocastro.dev`.
  Never a mockup, never a local run with seeded data — the point is that the
  screen is the production one.
- **Light theme.** The deck is paper; a dark screenshot fights the page. The
  console's theme toggle is the moon icon, top right.
- **Viewport 1600×1000, device scale 1**, so the image lands at the deck's own
  1600px stage width and stays sharp without inflating deck.html.
- **File name = the screen**, lower case, no dates: `pipeline.png`,
  `sessions.png`. One file per screen; if a slide needs a different state of the
  same screen, suffix it (`sessions-phone.png`).
- **Real data only.** Every session id, cost and score visible here belongs to a
  call that actually happened.

## Capturing one

The `sshot` MCP was broken when these were taken (its Playwright browser was a
version behind), so they were captured by driving Chromium directly. This is the
exact command, and it needs nothing installed:

```bash
CH="$HOME/.cache/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-mac-arm64/chrome-headless-shell"
# or: CH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

"$CH" --headless --disable-gpu --hide-scrollbars \
      --window-size=1600,1000 \
      --virtual-time-budget=9000 \
      --screenshot=presentation/screenshots/<name>.png \
      "https://lk.bernardocastro.dev/<path>"
```

`--virtual-time-budget` is not optional: the console is a React SPA that fetches
its data after first paint, and without it you capture an empty shell.

## What is here

| file | URL | what it proves | wanted by |
|---|---|---|---|
| `pipeline.png` | `/t/clinica-norte/pipeline` | the three legs of a turn as configuration, per project, with the allow-list and the models the platform *refuses* to run | 08 · 13 |
| `sessions.png` | `/t/clinica-norte/sessions` | one row per conversation across voice, phone and chat — with score, turns, events and **cost in euros** | 07 · 12 |
| `session-detail.png` | `/t/clinica-norte/sessions/AJ_rdrkYph3FaeS` | the append-only log of one call: latency per leg, the consent proof (`seq 39 asked; seq 46 authorised; seq 51`), and the five checks that scored it | 06 · 07 · 12 |
| `evals.png` | `/evals` | eval runs per project and per suite with the **delta against the previous run** of the same suite | 12 · 14 |
| `supervisor.png` | `/supervisor` | listen / whisper / takeover, and that the capability lives in the ticket rather than in a control on the screen | 10 |

## What is still missing

| file | where from | exact instruction |
|---|---|---|
| `board.png` | the taskops board — **not** on `lk.bernardocastro.dev`, which is the console | Open the board UI for this repo (`taskops ui` from `/Users/berna/prueba-abai`, default `http://127.0.0.1:7777`), show the milestone list with ms-0…ms-16 and the cards of one milestone expanded, then capture it with the command above pointed at that local URL. Wanted by slide 14 (roadmap: the phases are not a plan, they are a log). |

Until it exists, slide 14 carries the `.shot-missing` placeholder, which prints
that instruction into the PDF so nobody ships a hole by accident.

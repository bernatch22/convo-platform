# ms-9 — the console: three channels on screen, the pipeline visible and governable

**Landed 2026-08-31 · 8 cards (3 by the orchestrator, 5 by Opus workers) · lands on master with this milestone**

## What we set out to do

Give the platform its face — one React app that serves the three channels
(WebRTC voice, LLM-only chat, inbound telephone) and puts on screen what until
tonight only the terminal knew: the live transcript with STT interims and TTS
karaoke, the seq timeline with the consent proof, the three providers with
their measured latencies, and the first controls that change a call without a
deploy. Plus the thing the human asked for in so many words at 1 a.m.:
watching the pipeline breathe — when a transcription arrives, when the reply
starts generating — first in the terminal, then in the browser.

## What we achieved

- **`convo sessions tail`** — the pipeline live in the terminal: each event as
  it lands with the wall clock, `stt.final`, listening→thinking→speaking,
  `tts.word`, the ttft/e2e chips per turn. Run it on the box, call the number,
  watch.
- **A chat session opens zero voice connections.** `build_session` gates
  providers on the channel, not on key presence; the console's env fallback is
  honestly `voice` now. Found in the process: a test named "…is a voice
  session" had been building a chat context all along — the gate it needed
  didn't exist, so it passed.
- **The read side and the pipeline API**: `/sessions`, `/sessions/{id}`,
  `/sessions/{id}/live` (SSE), `/pipeline` GET/PUT (voice, tts_model,
  greeting — stored, applied by the router on the next session, forbidden
  models refused with the platform's own sentence), `/live-calls`, `/observe`
  (subscribe-only, hidden). Medians are measured or `null`, never zero.
- **The shell**: react-router data router, tenant switcher where the URL is
  the state, one tokens.css — near-black grounds, three inks, ONE lime accent
  spent only on what is live. Six screens, honest empty states.
- **Talk**: raw `livekit-client`, one wire model for both transcript cadences
  (a segment's text is what its most recent stream accumulated), interim grey
  → final, agent karaoke at audio pace, state chip, the live turn/tool
  timeline via SSE — and the LIVE NOW strip: any active call, phone included,
  joined as a hidden observer and rendered with exactly the same instrument.
- **Sessions**: the call log (phone calls first-class, caller number in
  accent) and the seq timeline with the latency strip matching the CLI digit
  for digit, cost by model, the folded sip.* map, and the consent proof drawn
  in both directions, joined on the ConfirmTask audience — "seq 49 authorised
  seq 54" is on screen now.
- **Pipeline**: HEARS / DECIDES / SPEAKS. Every knob with its one-line why,
  the cache floor stated, forbidden models struck through with the refusal
  sentence, the anatomy-of-a-turn waterfall from real medians (end of turn
  379ms · transcription 167ms · **llm ttft 1583ms** · tts ttfb 223ms · e2e
  2384ms), and the control form — proven by changing voice and greeting from
  the browser and hearing the next session open with them.

## What we learned the hard way

1. **Judge-backed tests inside the unit ring were phoning Anthropic on every
   run** — the "fast" suite took 4 minutes and cost money each time, for
   months. The night's first incident (a new judged test hanging the suite,
   four zombie pytests piling up) was the acute form. Structural fix: the unit
   ring swaps provider keys for a dead sentinel — construction works, a real
   call dies in seconds. 1.6s keyless. Never discipline, always structure.
2. **deepeval's ToolCorrectnessMetric is deterministic yet constructs an
   OpenAI judge** and demands a key it never uses. CI (which has no .env)
   found it on the repo's first day on GitHub. The sentinel covers
   OPENAI_API_KEY too.
3. **Being the first consumer finds seam bugs no test wrote.** The Talk card
   caught EventSource's own "open" event colliding with our `event: open` SSE
   frame, and `core/rooms.py` demanding a LIVEKIT_URL that `core/auth.py` had
   always defaulted — tokens minted for rooms the same process then 503'd
   about.
4. **The two transcript cadences are one rule.** Soniox interims arrive as
   whole non-delta streams re-using the segment id; the agent arrives as one
   delta stream. "A segment's text is what its most recent stream accumulated"
   renders both, and the karaoke and the interim grey are the same component.
5. **Three cards on one ui/ tree merge only if the seams were real.** app.css
   would have been a three-way conflict by construction; each screen carried
   its own sheet, and the only conflicts were router.tsx's import lists —
   resolved keeping every screen's loader and Talk's lazy import (livekit is
   half the bundle; only the screen that talks downloads it).

## Decisions

- **Raw livekit-client, validated.** The whole client protocol fits in three
  small libs a reviewer reads in one tab each; the components package would
  have hidden exactly the flow this test judges.
- **No UI test suites — the human tests the UI personally** (his rule, his
  words). Gates are tsc strict and a clean build; screenshots exist for the
  worker's own eyes, in tmp/, never in tests.
- **The consent proof joins on the token audience, not adjacency** — a yes to
  another tool can never be misread as authorising this one, on screen as in
  the guard.
- **`phone` became a field of GET /sessions**: channel says "voice" for a
  browser call and a PSTN call alike; the caller's number is the only honest
  discriminator an operator scanning the log has.
- **The SIP fold shows accountSid/callSid unmasked** — acceptable on an ops
  console, flagged for hardening before any customer-facing deploy.

## Where we stand

The platform has a face that proves its claims: the consent chain is visible,
the latency anatomy is drawn from measured medians, an inbound phone call can
be watched live — interims, karaoke, tools, timings — by someone who never
picked up a browser microphone, and the first three controls change the next
call with no deploy. Chrome-microphone voice and observing a REAL Twilio call
are wired but need the human's morning: both ride the observer path that was
proven live on a web room tonight.

Try it:

```bash
cd ui && npm install && npm run build && cd ..
uv run uvicorn api:app --port 8090
env -u TENANT -u PROJECT uv run python worker.py dev     # third terminal
open http://localhost:8090                                # talk, watch, control
# call +1 417 674 3169 and click its row under LIVE NOW
```

## What comes next

**ms-10** — the box completes: the UI served publicly, TURN/TLS on 443 for
WebRTC from mobile networks (the "webrtc is a capability, not a page"
conversation), MinIO for recordings, worker deploy formalised. Then **ms-15**
supervisor (listen, whisper, takeover — the observer path grown teeth),
**ms-7+13** evals with their screen, **ms-12** remote tools (a conversation
first), **ms-16** the presentation.

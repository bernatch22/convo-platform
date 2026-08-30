# @pinecall/stage — a page that talks

A presentation where the **page speaks** and the visitor can interrupt it and ask.
Not an audio file: a live Pinecall voice session whose mouth the page borrows,
word by word, and whose ear the visitor can open at any moment.

Two things make it more than TTS:

1. **The page speaks with the agent's mouth.** Every paragraph the page says
   enters the agent's history as its own turn, so when the visitor turns the mic
   on, the agent has *already said* the presentation and answers in context.
2. **Nothing is on a timer.** Words light up as they are heard, elements appear
   when the voice actually stopped, and the deck advances when the audio has
   really finished — reported by the server, not estimated by the browser.

> **Status: working prototype**, running against the deployed voice server.
> `tmp/stage-demo` is where it is being designed before it becomes the package.
> What is verified and what is not is listed at the bottom — read it.

---

## Run it

```bash
cd ~/bc-v2/tmp/stage-demo
set -a && . ~/bc-v2/.env && set +a          # PINECALL_API_KEY
PORT=4610 STAGE_SLUG=dev-berna-stage-deck node server.mjs
# → http://127.0.0.1:4610
```

`.env` carries `PORT=4322` for the site, so `PORT` **must** be overridden here.

---

## The architecture, in one pass

```
browser                                  your server                voice.pinecall.io
───────                                  ───────────                ─────────────────
<pinecall-stage>  ──── GET /token ───▶   mint with the API key ───▶  /webrtc/token
      │                                  (say budget, agent slug)
      │  POST /webrtc/offer  ────────────────────────────────────▶   session opens
      │  ◀──── answer ────────────────────────────────────────────
      │
      │  DataChannel  {say:{id,text,history}}  ──────────────────▶   TTS speaks
      │  ◀──  say.start · bot.word(say_id) · say.played · say.end
      │  ◀──  audio (recvonly, one audio transceiver)
      │
      │  {action:"upgrade_mic",sdp}  ────────────────────────────▶   renegotiation
      │  ◀──  mic.answer  → the SAME session now listens
```

**The API key never reaches the browser.** The token is minted server-side, once
per session, and carries the say budget. A page cannot raise its own budget.

---

## Elements

### `<pinecall-stage>`

The host. Owns the session — one per page, opened lazily on the first `say()`.

| attribute | meaning |
|---|---|
| `token-endpoint` | where to `GET` `{token, server}`. Default `/token` |

| property | type | meaning |
|---|---|---|
| `rms` | number | live output level, 0…1 — what the ear steers by |
| `hearing` | boolean | **false = the analyser is parked** and every level reads 0 |
| `lag` | number | ms between asking for a say and its first audible sample |
| `token`, `server`, `pcId` | | the session's identifiers, after connect |

| method | what it does |
|---|---|
| `connect()` | opens the session. Idempotent — every caller awaits the same promise |
| `say(el, text, {history=true})` | speak `text`, route its words to `el` (or `null`), resolve **when it has been heard** |
| `silence()` | cancel: drop the queue and cut the utterance in flight, server-side |
| `enableMic()` | upgrade this session to sendrecv and resolve when the mic is really live |

`dataset.state` is `idle` → `connecting` → `live`; `dataset.mic` is `on` once the
upgrade completed.

### `<tts-paragraph>`

A paragraph the page speaks.

| attribute | meaning |
|---|---|
| `display="karaoke"` | words appear and light as they are spoken (default) |
| `display="hidden"` | nothing on screen — the voice **is** the content |
| `reveals="#id"` | that element gets `.is-revealed` at the start, and a `--say-progress` custom property advanced 0→1 **by the voice** |
| `after="#id"` | that element gets `.is-revealed` when the voice has **finished** |
| `history="off"` | do not put this paragraph in the agent's history |

| method | what it does |
|---|---|
| `say()` | speak me; resolves when heard |
| `reset()` | back to unspoken, same words — for replaying a slide |

Emits `say.word` per word and `say.finished` at the end (both bubble).

CSS hooks: `.w`, `.w.spoken`, `.w.speaking` on each word; `.is-speaking` /
`.is-spoken` on the element; `--say-progress` on the `reveals` target.

**The unspoken words are `display:none` on purpose** — the text writes itself at
the pace of the voice instead of sitting there greyed out. Give the block a
`min-height` so the slide does not jump as it grows.

### `<pinecall-mic>`

A button that opens the visitor's microphone on the **same** session — no second
token, no new session, the history survives.

| attribute | meaning |
|---|---|
| `label` | the button text |

On failure it re-arms itself and shows the server's own reason (`no audio track`,
a timeout, a denied permission) instead of a dead "mic on".

### `<stage-scene>` — choreography

Its children run **in order**, each awaited. The order in the HTML *is* the order
of the presentation, so "show it, then explain it" and "explain it, then show it"
are the same feature: you move a line.

```html
<stage-scene>
  <stage-show for="#chart"></stage-show>
  <tts-paragraph>This is the chart, and it appeared before I said this.</tts-paragraph>
  <stage-wait s="3"></stage-wait>
  <stage-show for="#legend"></stage-show>
  <tts-paragraph>The green line is the one that matters.</tts-paragraph>
  <stage-ask s="6">Any questions?</stage-ask>
  <stage-count from="3"></stage-count>
  <stage-next></stage-next>
</stage-scene>
```

| step | attributes | what it does |
|---|---|---|
| `<tts-paragraph>` | see above | speaks, and the scene **waits until it was heard** |
| `<stage-show>` | `for="#id"`, `after=ms` (350) | adds `.is-revealed`, then holds `after` ms so the sentence does not start before the element is visible |
| `<stage-hide>` | `for="#id"` | removes `.is-revealed` |
| `<stage-wait>` | `s=seconds` | silence, on purpose |
| `<stage-count>` | `from=3`, `gap=ms` (250) | counts down **out loud**, one say per number |
| `<stage-ask>` | `s=seconds` | speaks its text, opens the mic, then listens for `s` seconds |
| `<stage-next>` | — | fires `stage.scene.next` (bubbles) for the deck to advance |

`scene.play()` runs it; `scene.cancel()` stops it **between steps and inside a
wait**, which is what makes jumping slides mid-scene instant.

---

## Events

Every frame the session receives is dispatched on `<pinecall-stage>` as
`stage.<event>`, plus these:

| event | when |
|---|---|
| `stage.live` | the session is open and the DataChannel is up |
| `stage.frame` | **every** frame, raw, before any routing — the debug tap |
| `stage.say.played` | the server finished sending this say's audio |
| `stage.reply.word` | a `bot.word` that belongs to the agent's own turn, not to a paragraph |
| `stage.mic.on` | the mic upgrade completed |
| `stage.scene.next` | a `<stage-next>` step ran |

Useful pass-throughs from the server: `stage.user.message` (what the visitor
said), `stage.bot.speaking` (carries the reply's text), `stage.turn.pause`,
`stage.turn.end`, `stage.mic.error`.

**There is no `llm.chat.done`.** The agent's reply arrives as `bot.speaking` plus
a `bot.word` stream. Listening for an event the server does not have is how a
session that was answering perfectly looked completely dead.

---

## When is the audio over?

The single hardest question in this design, and it has three answers ranked by
how much they actually know:

| source | what it means | trustworthy? |
|---|---|---|
| **`say.played`** | the server's output track ran out of audio; carries `playout_ms` (300) still in flight to the visitor | **yes — use this** |
| the ear (`rms`) | an analyser over the received stream says the room went quiet | only while `stage.hearing` is true |
| a fixed tail | 700 ms after `say.end` | last resort |

`say()` races them, so a server without `say.played` degrades instead of hanging.

**What `say.end` does NOT mean:** it is *synthesis* finished. TTS outruns playout
by seconds, so advancing a deck on `say.end` runs the slide ahead of the voice.

**Why the ear alone is not enough:** the analyser's `AudioContext` starts
`suspended` if it is created after the click's gesture expired, and then reads a
constant 0 — indistinguishable from silence. The stage resumes it on every
`pointerdown`/`keydown`, and `stage.hearing` tells you when it is deaf.

---

## Server-side contract (`@pinecall/sdk` + the voice server)

### The token

Minted with the org key, one per session. Claims the browser can **never** set:

| claim | meaning |
|---|---|
| `say` | characters this page may speak (the demo uses 8000) |
| `greet` | a per-session greeting |
| `kb` | a per-session knowledge base |

The SDK's `createToken` **drops unknown params in silence** — mint by calling
`/webrtc/token` directly, as `server.mjs` and bc-v2's `mint.ts` both do.

### DataChannel commands

| command | shapes |
|---|---|
| speak | `{say:{id,text,history}}` or `{action:"say",…}` |
| cancel | `{action:"say.cancel"}` or `{say:{cancel:true}}` |
| mic | `{action:"upgrade_mic",sdp,type}` |

### Agent registration

```js
pc.agent(SLUG, {
  prompt: PROMPT,              // embeds the deck as <presentation> XML
  llm: "openai/gpt-5.4-nano",
  voice: "elevenlabs/matilda",
  stt: "deepgram/flux-en",     // ← DECLARE IT. See below.
  language: "en",
  // NO greeting: a stage session opens silent — the PAGE speaks first.
})
```

**Declare `stt` explicitly.** Left unset, the two halves of the session disagree:
the STT client defaults to `deepgram-flux` (read from `raw_config`) while turn
detection is derived for plain `deepgram` → `smart_turn` + `silero`. Flux's own
`StartOfTurn` is then discarded (`start_ignored reason=using_local_vad`) and the
local VAD closes the turn asking flux for a transcript it never committed. The
visitor speaks and the turn arrives as `"."`. Naming flux makes the derivation
pick its native turn (`config.auto_derived stt=deepgram-flux turn=native
vad=native`) and both halves agree.

**No greeting.** An agent that says hello first talks over the first paragraph
(the say queues behind it) while the slide highlights words nobody is hearing.

---

## Debugging

The demo page has a **frames panel**: every DataChannel frame in order, with its
payload; `bot.word` and metrics collapse into one counted line. Build it from
`stage.frame` — three separate bugs were invisible without it.

Read it like this:

| symptom in the panel | what it means |
|---|---|
| no `mic.answer` after enabling the mic | the renegotiation never completed |
| `user.message` with empty text | the mic works, the **STT** produced nothing (see `stt`) |
| `bot.speaking` arrives but you hear nothing | the audio path, not the agent |
| `audio 0.000 (DEAF)` in the meter | the AudioContext is parked; the ear is blind |

Server-side, on the voice box: `/tmp/pinecall-stt.log` (what STT decoded),
`/tmp/webrtc_debug.log` (every DataChannel frame with timestamps),
`/tmp/pinecall-calls.log` (`audio.interrupt`, `audio.tts_stopped`),
`/tmp/llm.log` (the history the model actually saw).

---

## Verified

Against the deployed server, on 2026-08-17:

- the page speaks, karaoke lights word by word, `--say-progress` animates off the voice
- `after="#id"` reveals when the voice really stopped
- **cancel**: changing slide mid-sentence cuts the audio and the next slide starts
  in ~59 ms (it was 4.3 s — three separate causes, all fixed and all commented in
  the code so they are not retried)
- the mic upgrade completes on the same session and the visitor's speech
  transcribes (`visitor: It's only about the presentation.`)
- `say.played` fires on the drained edge (test on the box), `flush()` 6/6,
  the `say` suite 80/80

## Not verified yet

- `<stage-ask>` end to end — written and syntax-checked, never used by voice
- `<stage-count>` audibly (each number is its own say; the gap may want tuning)
- anything on mobile Safari, where the AudioContext rules are stricter

## Known platform gaps

- **barge-in has the same buffered-audio problem the say cancel had**:
  `audio_processor.interrupt()` stops synthesis and does not flush the output
  track, so an interrupted bot keeps talking for whatever was queued.
  `RawAudioOutputTrack.flush()` exists now and would fix it — deliberately not
  wired into the call path yet.
- the STT/turn-detection default disagreement described above affects **any**
  agent that does not declare `stt`. The root fix is one source of truth for the
  provider; which default wins is a platform decision.
- `createToken` in the SDK still does not know `knowledge_base` / `greeting` /
  `say`.

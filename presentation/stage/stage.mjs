// The three elements of @pinecall/stage, at prototype scale and with no
// framework — written against the raw WebRTC API and the server's own
// DataChannel so the proof does not depend on the package existing yet.
//
//   <pinecall-stage>   the host: ONE lazy session per page, born audio
//                      RECEIVE-ONLY (no microphone permission asked), speaking
//                      through the `say` command.
//   <tts-paragraph>    a paragraph the page SPEAKS instead of showing. Karaoke,
//                      hidden, or a reveal driven by the voice's own timing.
//   <pinecall-mic>     turns the same session into a conversation.
//
// WHY THE SESSION IS LAZY AND NOT EAGER: a browser will not play audio before a
// gesture, so a session opened on load would speak into a muted tab. The first
// click IS the permission.

class PinecallStage extends HTMLElement {
  #pc = null;
  #dc = null;
  #audio = null;
  #ready = null;
  /** id → the tts-paragraph waiting for its words. */
  #speaking = new Map();
  /** The paragraph whose say is between say.start and say.end — and only then. */
  #voicing = null;
  /** id of the say currently voicing, so late words of a DIFFERENT say drop. */
  #voicingId = null;
  #queue = [];
  /** say id → resolve(), fired when the server reports the audio fully sent. */
  #played = new Map();
  /** says that were cancelled (pause / slide change) — their late words drop,
   *  and their paragraph freezes where it is instead of filling the tail. */
  #cancelledSays = new Set();
  #micTrack = null;
  /** The analyser's AudioContext — deaf while it is not "running". */
  #ctx = null;
  /** Resolvers for the in-flight `upgrade_mic` renegotiation, if any. */
  #micPending = null;
  /** RMS of the audio actually coming out of the speaker, 0..1. */
  #level = () => 0;
  /** ms between asking for a say and its first audible sample — reported, not used to time paint. */
  lag = 0;

  connectedCallback() {
    this.dataset.state = "idle";
    // Any gesture is a chance to wake the ear: browsers only let an
    // AudioContext resume from one, and the stage is useless deaf.
    for (const ev of ["pointerdown", "keydown"]) {
      addEventListener(ev, () => this.#wake(), { passive: true });
    }
  }

  /** Resume the analyser's context if the browser parked it. */
  #wake() {
    if (this.#ctx && this.#ctx.state !== "running") this.#ctx.resume?.().catch(() => {});
  }

  /** True when the ear is actually able to hear (a suspended context is deaf). */
  get hearing() {
    return this.#ctx?.state === "running";
  }

  /** Open the session, once. Every caller awaits the same promise. */
  connect() {
    if (this.#ready) return this.#ready;
    this.#ready = (async () => {
      this.dataset.state = "connecting";
      const { token, server } = await fetch(this.getAttribute("token-endpoint") || "/token").then(
        (r) => r.json(),
      );

      const pc = new RTCPeerConnection({
        iceServers: [{ urls: "stun:stun.l.google.com:19302" }],
      });
      this.#pc = pc;

      // RECEIVE-ONLY: no getUserMedia, so the browser asks for nothing. The
      // microphone arrives later, on the same transceiver, if the visitor wants
      // to talk (see enableMic).
      pc.addTransceiver("audio", { direction: "recvonly" });

      const audio = new Audio();
      audio.autoplay = true;
      this.#audio = audio;
      pc.ontrack = (e) => {
        audio.srcObject = e.streams[0];
        audio.play().catch(() => {});
        // THE EAR. say.end means "the server finished synthesizing", not
        // "the visitor finished hearing it" — the words are still in the
        // jitter buffer and in the element's own playout. Advancing a deck on
        // say.end therefore runs one slide AHEAD of the voice, which is
        // exactly what it looked like. So the stage measures the OUTPUT: an
        // analyser over the remote stream tells us when the mouth is really
        // quiet, and nothing moves until it is.
        try {
          const ctx = new (window.AudioContext || window.webkitAudioContext)();
          const src = ctx.createMediaStreamSource(e.streams[0]);
          const an = ctx.createAnalyser();
          an.fftSize = 512;
          src.connect(an);
          const buf = new Float32Array(an.fftSize);
          this.#level = () => {
            an.getFloatTimeDomainData(buf);
            let sum = 0;
            for (const v of buf) sum += v * v;
            return Math.sqrt(sum / buf.length);
          };
          // Exposed so a page can SHOW what the stage steers by — the panel in
          // the demo reads exactly this number.
          Object.defineProperty(this, "rms", { get: () => this.#level(), configurable: true });
          // Kept, because ONE resume is not enough: a context created after the
          // click's gesture has expired starts `suspended` and hands out
          // ZEROS forever. The stage then never hears its own voice, decides
          // nothing was ever spoken, and falls back to a blind wait — measured
          // as a 9 s gap between slides while the audio played fine.
          this.#ctx = ctx;
          this.#wake();
        } catch (err) {
          console.warn("[stage] no analyser — falling back to say.end timing", err);
        }
      };

      const dc = pc.createDataChannel("pinecall");
      this.#dc = dc;
      dc.onmessage = (e) => this.#onFrame(e.data);

      await pc.setLocalDescription(await pc.createOffer());
      await new Promise((done) => {
        if (pc.iceGatheringState === "complete") return done();
        const t = setTimeout(done, 1200); // trickle is not needed for one hop
        pc.onicegatheringstatechange = () => {
          if (pc.iceGatheringState === "complete") {
            clearTimeout(t);
            done();
          }
        };
      });

      const answer = await fetch(new URL("/webrtc/offer", server), {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ sdp: pc.localDescription.sdp, type: "offer", token }),
      }).then((r) => r.json());
      await pc.setRemoteDescription({ sdp: answer.sdp, type: "answer" });
      this.pcId = answer.pc_id ?? answer.pcId ?? null;
      this.token = token;
      this.server = server;

      await new Promise((done) => {
        if (dc.readyState === "open") return done();
        dc.onopen = done;
      });
      this.dataset.state = "live";
      this.dispatchEvent(new CustomEvent("stage.live"));
    })();
    return this.#ready;
  }

  /** Speak `text` and route its words back to `el`. One mouth: it queues. */
  async say(el, text, { history = true, voice = null } = {}) {
    await this.connect();
    const id = "s" + Math.random().toString(36).slice(2, 10);
    // Clean slate: a re-spoken paragraph (resume) must start unpainted, or it
    // highlights from wherever it was left.
    el?.restart?.();
    if (el) this.#speaking.set(id, el);
    // Armed BEFORE the command goes out: `say.played` can land while we are
    // still awaiting say.end, and a resolver registered afterwards misses it.
    const played = new Promise((resolve) => this.#played.set(id, resolve));
    // `voice` is honored server-side (webrtc): the say is spoken in that voice
    // and the narration voice is restored after — used for a title in another
    // voice. Omitted → the agent's own voice.
    const cmd = { id, text, history };
    if (voice) cmd.voice = voice;
    this.#dc.send(JSON.stringify({ say: cmd }));
    const synthesized = new Promise((resolve) => {
      this.#queue.push({ id, resolve });
    });
    const ok = await synthesized;
    // say.end means "synthesized", so what is left is playout: wait for real
    // silence (900 ms — an inter-sentence pause in one paragraph is shorter;
    // 420 ms was not, and cut a paragraph 4.3 s early, measured) and for the
    // paragraph to have painted everything it received.
    // say.end now lands after the last word (the server waits for the speech to
    // start before waiting for it to end — fixed in _speak_say), so the only
    // thing left after it is the playout buffer: a short tail, not a guess.
    // WHO DECIDES THE AUDIO IS OVER, in order of how much they actually know:
    //
    //  1. `say.played` — the server's output track ran out of audio. It is the
    //     real end of the utterance: `say.end` is only synthesis, which finishes
    //     seconds earlier because TTS outruns playout. The frame carries
    //     `playout_ms`, what is still in flight to the visitor, so the page
    //     waits that out instead of inventing a number.
    //  2. the ear — an analyser over the received stream. Right when it works,
    //     useless when the browser parks the AudioContext (a constant 0 reads as
    //     eternal silence).
    //  3. a short fixed tail, when neither is available.
    // RACED, never awaited alone: a server that does not send `say.played`
    // (an older one, or the chat transport) must not hang the presentation.
    const fallback = this.hearing
      ? this.#untilQuiet({ hold: 550 })
      : new Promise((r) => setTimeout(r, 700));
    await Promise.race([played, fallback]);
    this.#played.delete(id);
    this.#speaking.delete(id);
    // Cancelled (pause / slide change): FREEZE where it stopped, do not fill the
    // tail — filling is the cascade that made a pause dump the whole paragraph.
    // A natural end settles the tail as usual.
    if (this.#cancelledSays.has(id)) {
      this.#cancelledSays.delete(id);
      el?.freeze?.();
    } else {
      el?.finished?.(null);
    }
    if (this.#voicing === el) { this.#voicing = null; this.#voicingId = null; }
    return ok;
  }

  /**
   * Shut up: drop everything queued and cut the utterance in flight.
   *
   * The mouth is ONE. A deck that changes slide without this leaves the
   * abandoned paragraph playing AND makes the new slide's paragraph queue
   * behind it — the visitor looks at slide 2 and hears slide 1 to the end.
   * The server owns the audio, so only the server can stop it: `say.cancel`
   * clears its queue and interrupts the TTS through the same path barge-in
   * uses. Every say we were awaiting comes back as `say.error cancelled`,
   * which resolves the promises instead of leaving them hanging.
   */
  async silence() {
    if (!this.#dc || this.#dc.readyState !== "open") return;
    // Nothing is speaking or queued → do NOT send a cancel. A spurious
    // say.cancel fires the server's audio interrupt over the NEXT utterance
    // that is just starting, cutting it (measured: a title cut to 0.4 s right
    // after a slide change, from a second cancel with no say in flight).
    if (!this.#voicingId && this.#queue.length === 0) return;
    // Mark everything in flight/queued as cancelled BEFORE the command: their
    // late words must drop (not paint the next paragraph) and their paragraphs
    // must freeze, not fill. The current voicing say and every queued one.
    if (this.#voicingId) this.#cancelledSays.add(this.#voicingId);
    for (const q of this.#queue) this.#cancelledSays.add(q.id);
    this.#dc.send(JSON.stringify({ action: "say.cancel" }));
    // Local state goes now, not on the echo: the caller is about to speak the
    // next paragraph and must not route its words into the abandoned one.
    this.#voicing = null;
    this.#voicingId = null;
  }

  /**
   * Resolve when the speaker has been quiet for `hold` ms.
   *
   * `min` guards the head of a say (audio has not started yet, so silence is
   * not "finished"); `hold` is what tells a pause inside a sentence from the
   * end of one. Both are wall-clock, both cheap: this only runs while a
   * paragraph is being spoken.
   */
  async #untilQuiet({ hold = 900, min = 500, max = 120_000, settled = () => true } = {}) {
    const started = performance.now();
    let quietSince = 0;
    let heard = false;
    for (;;) {
      await new Promise((r) => requestAnimationFrame(r));
      const now = performance.now();
      const rms = this.#level();
      if (rms > 0.006) {
        if (!heard) {
          heard = true;
          this.lag = Math.round(now - started); // audible - requested
        }
        quietSince = 0;
      } else if (heard) {
        quietSince ||= now;
        if (now - quietSince > hold && settled()) return;
      }
      if (now - started > max) return;
      // Nothing was ever heard: either the utterance was silent or the ear went
      // deaf mid-say (the context can be parked at any time). 2 s, not 8.5 —
      // long enough for a slow first sample, short enough not to read as frozen.
      if (!heard && now - started > min + 2000) return;
    }
  }

  /**
   * The microphone, on the SAME session — the contract the server's recvonly
   * card defined: replaceTrack on the transceiver we already have, flip it to
   * sendrecv, offer again, hand the SDP over the open DataChannel, apply the
   * answer. No new token, no new session, the history stays.
   */
  async enableMic() {
    await this.connect();
    if (this.#micTrack) return true;
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const track = stream.getAudioTracks()[0];
    const tx = this.#pc.getTransceivers().find((t) => t.receiver.track?.kind === "audio") ??
      this.#pc.getTransceivers()[0];
    await tx.sender.replaceTrack(track);
    tx.direction = "sendrecv";
    this.#micTrack = track;

    const offer = await this.#pc.createOffer();
    await this.#pc.setLocalDescription(offer);

    // AND THEN WAIT FOR THE ANSWER, WHICH IS THE HALF THAT WAS MISSING.
    // Sending the offer is not the upgrade — an offer with no answer applied
    // leaves the PeerConnection in `have-local-offer` forever: the mic track
    // exists, the direction says sendrecv, the button says "just talk", and
    // not one packet is ever sent because the negotiation never completed.
    // Nothing throws, which is why it looked like the server ignoring us.
    const answer = new Promise((resolve, reject) => {
      this.#micPending = { resolve, reject };
      setTimeout(() => reject(new Error("mic upgrade timed out")), 10000);
    });
    this.#dc.send(
      JSON.stringify({ action: "upgrade_mic", sdp: this.#pc.localDescription.sdp, type: "offer" }),
    );

    try {
      await answer;
    } catch (e) {
      // Leave no half-upgrade behind: drop the track so a second click is a
      // clean retry rather than an early `return true` on a dead mic.
      this.#micTrack = null;
      track.stop();
      await tx.sender.replaceTrack(null).catch(() => {});
      delete this.dataset.mic;
      throw e;
    } finally {
      this.#micPending = null;
    }

    this.dataset.mic = "on";
    this.dispatchEvent(new CustomEvent("stage.mic.on", { bubbles: true }));
    return true;
  }

  #onFrame(raw) {
    let d;
    try {
      d = JSON.parse(raw);
    } catch {
      return;
    }
    const ev = d.event ?? d.type;

    // EVERY frame, raw, before any routing decides to swallow it. Without this
    // the page could only see the events somebody remembered to re-dispatch —
    // which is how a session that was answering fine looked completely dead:
    // the reply arrives as bot.speaking + bot.word, and nothing was listening.
    this.dispatchEvent(new CustomEvent("stage.frame", { detail: d }));

    // The other side of the mic upgrade. `mic.error` carries the server's own
    // reason (no sdp / no audio track / renegotiation failed) — surface it
    // instead of a timeout, so a refusal reads as a refusal.
    if (ev === "mic.answer") {
      this.#pc
        .setRemoteDescription({ sdp: d.sdp, type: "answer" })
        .then(() => this.#micPending?.resolve())
        .catch((e) => this.#micPending?.reject(e));
      return;
    }
    if (ev === "mic.error") {
      this.#micPending?.reject(new Error(d.error + (d.detail ? `: ${d.detail}` : "")));
      return;
    }

    // The words of a say carry its id — that is how a page with four speaking
    // paragraphs knows which one is being spoken right now.
    // ONE MOUTH, so a word that lands while our say is in flight belongs to it.
    // `say_id` tags them when the server has one to tag with, but it is not
    // always there on this path (measured: say.start arrived, 31 words arrived,
    // none tagged) — and a stage that only trusted the tag lit nothing at all.
    // The tag is used when present and the in-flight say is the fallback; both
    // are correct because a session speaks one thing at a time.
    if (ev === "bot.word") {
      const sid = d.say_id;
      if (sid) {
        // A word from a CANCELLED say (paused, or a slide left behind) must be
        // dropped — otherwise its late frames paint whatever paragraph is now
        // speaking, which is the "highlights something that isn't" on resume.
        if (this.#cancelledSays.has(sid)) return;
        const el = this.#speaking.get(sid);
        if (el) el.word?.(d);
        else this.dispatchEvent(new CustomEvent("stage.reply.word", { detail: d }));
        return;
      }
      // Untagged word: route to the paragraph currently voicing (server does not
      // always tag). silence() clears #voicing, so words after a cancel drop.
      if (this.#voicing) {
        this.#voicing.word?.(d);
        return;
      }
      // Nobody voicing → the agent's OWN turn (the mic conversation).
      this.dispatchEvent(new CustomEvent("stage.reply.word", { detail: d }));
      return;
    }
    // The audio of this say has fully left the server. What remains is the
    // visitor's own buffer, which the server reports as `playout_ms`.
    if (ev === "say.played") {
      const resolve = this.#played.get(d.id);
      if (resolve) setTimeout(resolve, Number(d.playout_ms ?? 300));
      this.dispatchEvent(new CustomEvent("stage.say.played", { detail: d }));
      return;
    }
    if (ev === "say.start") {
      this.#voicing = this.#speaking.get(d.id) ?? null;
      this.#voicingId = d.id;
      this.#voicing?.started?.();
      return;
    }
    // `say.cancelled` is the utterance we asked the server to cut. It settles
    // like an end, not like an error: nothing failed, the visitor moved on. Left
    // unhandled, the promise for the say in flight never resolved.
    if (ev === "say.end" || ev === "say.error" || ev === "say.cancelled") {
      // NOT finished yet: say.end is the server's mouth closing, and the ear is
      // still hearing the buffer. `say()` settles the element after silence.
      // The route stays OPEN past say.end. Words are released at the pace of
      // the audio while say.end fires when synthesis finishes — closing here
      // orphaned every word still to be heard, and the paragraph stopped
      // highlighting. It closes when the ear says so (in `say`).
      if (ev === "say.error") this.#speaking.get(d.id)?.finished?.(d);
      this.#speaking.delete(d.id);
      const q = this.#queue.findIndex((x) => x.id === d.id);
      if (q >= 0) this.#queue.splice(q, 1)[0].resolve(ev !== "say.error");
      return;
    }
    // Anything the agent says on its OWN turn (the mic conversation) and the
    // turn phases go out as events for the page to render however it likes.
    if (ev) this.dispatchEvent(new CustomEvent("stage." + ev, { detail: d }));
  }
}

/**
 * A paragraph the page speaks.
 *
 *   display="karaoke"  each word lights as it is spoken (.spoken / .speaking)
 *   display="hidden"   nothing on screen — the voice IS the content
 *   reveals="#id"      that element gets .is-revealed and a --say-progress
 *                      custom property, 0→1, advanced by rAF between words:
 *                      animate anything in CSS off the voice's own pace
 */
class TtsParagraph extends HTMLElement {
  #words = [];
  /** Word frames received from the server (ahead of the ear). */
  #received = 0;
  /** Words actually painted (on the ear). */
  #spoken = 0;

  #raf = 0;
  #target = null;
  /** Revealed once the voice has finished, via after="#id". */
  #after = null;
  #progress = 0;

  connectedCallback() {
    this.stage = this.closest("pinecall-stage");
    this.text = (this.textContent || "").replace(/\s+/g, " ").trim();
    this.display = this.getAttribute("display") || "karaoke";
    this.#target = this.getAttribute("reveals")
      ? document.querySelector(this.getAttribute("reveals"))
      : null;
    // `after="#id"`: that element enters when the voice has FINISHED — not at
    // say.end (the server's mouth closing, with audio still in the buffer) but
    // when the room is quiet, which is the moment the visitor stopped hearing.
    this.#after = this.getAttribute("after")
      ? document.querySelector(this.getAttribute("after"))
      : null;

    this.#build();
  }

  /**
   * Set (or replace) the words this paragraph speaks.
   *
   * REQUIRED whenever the text does not come from the markup. The element reads
   * its textContent ONCE, when the browser upgrades it — so a page that fetches
   * its script (the deck as JSON, an i18n dictionary) and assigns `textContent`
   * afterwards leaves this element holding an empty string, and `say()` sends ""
   * — which the server refuses with `say.error: invalid` and the page goes
   * silent with no other symptom.
   */
  setText(text) {
    this.text = String(text ?? "").replace(/\s+/g, " ").trim();
    this.#build();
    return this;
  }

  #build() {
    this.#words = [];
    if (this.display === "karaoke") {
      this.textContent = "";
      this.#words = (this.text ? this.text.split(" ") : []).map((w) => {
        const s = document.createElement("span");
        s.className = "w";
        s.textContent = w + " ";
        this.appendChild(s);
        return s;
      });
    } else if (this.display === "hidden") {
      this.textContent = "";
      this.hidden = true;
    }
  }

  /** Speak me. Returns when the voice is done. */
  say() {
    // Last line of defence: text assigned after the upgrade, with no setText().
    if (!this.text && (this.textContent || "").trim()) this.setText(this.textContent);
    if (!this.text) {
      console.warn("[stage] tts-paragraph has no text — use setText()", this);
      return Promise.resolve(false);
    }
    return this.stage.say(this, this.text, { history: this.getAttribute("history") !== "off" });
  }

  started() {
    this.classList.add("is-speaking");
    this.#target?.classList.add("is-revealed");
    this.#tick();
  }

  /**
   * One word arrived — PAINT IT AT ITS OWN TIME, not when the frame landed.
   *
   * The server paces `bot.word` against playback, but that pacing slips: a long
   * line synthesized in several TTS chunks bursts a whole run of frames at once,
   * and painting on arrival then dumps half the paragraph green in one tick —
   * which is exactly the bug ("todo de golpe y sigue reproduciendo audio").
   *
   * So the frame is not trusted to ARRIVE on time; its `start` (seconds into the
   * utterance, offset-adjusted by the server) is trusted instead. The first word
   * sets an anchor — wall-clock now paired with its own start — and every word
   * is painted at `anchor + (start - firstStart)`. Burst or paced, the karaoke
   * runs at the voice's own cadence. A word already past its time paints at once
   * (we were behind); a word ahead waits.
   *
   * Fallback: a server with no `start` in the frame (older) → paint on arrival,
   * the previous behaviour.
   */
  word(d) {
    // PAINT ON ARRIVAL. The server now paces `bot.word` against the audio it
    // has actually put on the wire (per chunk, anchored to real played ms), so a
    // frame arriving here IS the word being heard — the only correct thing to do
    // is paint it. The earlier client-side scheduling existed to compensate for
    // the server dumping bursts; with the server paced honestly it only fought
    // that pacing and re-introduced lag.
    this.#received++;
    this.#spoken = this.#received;
    this.#paint();
    this.dispatchEvent(new CustomEvent("say.word", { detail: d, bubbles: true }));
  }

  /** True once every received word has been painted. */
  caughtUp() {
    return this.#spoken >= this.#received && this.#received > 0;
  }

  #paint() {
    if (!this.#words.length) return;
    const i = Math.min(this.#spoken, this.#words.length) - 1;
    this.#words.forEach((w, n) => {
      w.classList.toggle("spoken", n < i);
      w.classList.toggle("speaking", n === i);
    });
  }

  /**
   * The reveal, and only the reveal: `--say-progress` eased toward the share of
   * words already heard, so an element animating off it moves continuously
   * between two words instead of stepping. The karaoke itself is not on a clock
   * — it is on the frames.
   */
  #tick() {
    cancelAnimationFrame(this.#raf);
    const total = this.text.split(" ").length;
    const step = () => {
      const aim = Math.min(1, this.#spoken / total);
      this.#progress += (aim - this.#progress) * 0.12;
      this.#target?.style.setProperty("--say-progress", this.#progress.toFixed(4));
      if (this.classList.contains("is-speaking")) this.#raf = requestAnimationFrame(step);
    };
    this.#raf = requestAnimationFrame(step);
  }

  /** Play me again: back to unspoken, keeping the same words. */
  reset() {
    this.#received = 0;
    this.#spoken = 0;
    this.#progress = 0;
    this.classList.remove("is-spoken", "is-speaking");
    this.#words.forEach((w) => w.classList.remove("spoken", "speaking"));
    this.#target?.classList.remove("is-revealed");
    this.#after?.classList.remove("is-revealed");
    this.#target?.style.setProperty("--say-progress", "0");
  }

  /** Clear the word highlight to speak again, KEEPING any reveals. Used when a
   *  paused paragraph is re-spoken on resume — it must start unpainted. */
  restart() {
    this.#received = 0;
    this.#spoken = 0;
    cancelAnimationFrame(this.#raf);
    this.classList.remove("is-spoken");
    this.#words.forEach((w) => w.classList.remove("spoken", "speaking"));
  }

  /** Stop where it is — no tail fill. The words already lit stay lit; the rest
   *  stay unpainted. This is what a pause looks like, instead of the cascade. */
  freeze() {
    cancelAnimationFrame(this.#raf);
    this.classList.remove("is-speaking");
  }

  finished(err) {
    // Called when the AUDIO is done (see stage.say) — safe to settle the tail.
    this.classList.remove("is-speaking");
    this.classList.add("is-spoken");

    // THE TAIL IS STAGGERED, never dumped. Whatever has not been painted is
    // written out fast but still one word at a time: a paragraph that lands its
    // last eight words in a single frame reads as a bug even when the audio was
    // fine, and it is how a false "it finished" gets noticed as "the karaoke
    // broke" instead of as the timing problem it actually is.
    const pending = this.#words.filter((w) => !w.classList.contains("spoken"));
    pending.forEach((w, n) => {
      setTimeout(() => {
        w.classList.add("spoken");
        w.classList.remove("speaking");
      }, Math.min(n * 45, 500));
    });
    this.#target?.style.setProperty("--say-progress", "1");
    this.#after?.classList.add("is-revealed");
    cancelAnimationFrame(this.#raf);
    this.dispatchEvent(new CustomEvent("say.finished", { bubbles: true }));
    if (err) console.warn("[stage] say failed", err);
  }
}

/**
 * A CHOREOGRAPHED SLIDE: its children run in order, each one awaited.
 *
 *   <stage-scene>
 *     <stage-show for="#chart"/>            reveal an element (img, div, anything)
 *     <tts-paragraph>Here is the chart…</tts-paragraph>     speak, and WAIT until heard
 *     <stage-wait s="3"/>                   hold, e.g. to let it sink in
 *     <stage-show for="#legend"/>
 *     <tts-paragraph>The green line is…</tts-paragraph>
 *     <stage-ask s="6">Any questions?</stage-ask>   speak, then listen for a while
 *     <stage-count from="3"/>               3… 2… 1… spoken out loud
 *     <stage-next/>                         advance the deck
 *   </stage-scene>
 *
 * The order in the HTML IS the order of the presentation, so "show it, then
 * explain it" and "explain it, then show it" are the same feature — you move the
 * line. Nothing here is on a timer except what you explicitly ask to be.
 */
class StageScene extends HTMLElement {
  #abort = null;
  /** Current step index — so pause can re-run the step it interrupted. */
  #i = 0;
  #paused = false;
  #resumers = [];

  /** Run the scene. Resolves when its last step is done, or when cancelled. */
  async play() {
    this.cancel();
    const run = { cancelled: false };
    this.#abort = run;
    this.#i = 0;
    this.#paused = false;
    const steps = [...this.children];
    this.classList.add("is-playing");
    try {
      while (this.#i < steps.length) {
        if (run.cancelled) break;
        await this.#step(steps[this.#i], run);
        if (run.cancelled) break;
        // PAUSED. The step just ran was cut short by pause() (it silenced the
        // voice), so hold here and — crucially — do NOT advance: on resume the
        // same step runs again, re-speaking what the visitor did not finish
        // hearing. Between-step pauses simply re-run the next step, which is
        // harmless (a reveal is idempotent, a line re-speaks).
        if (this.#paused) {
          await new Promise((r) => this.#resumers.push(r));
          continue;
        }
        this.#i++;
      }
    } finally {
      this.classList.remove("is-playing");
      this.#paused = false;
      if (this.#abort === run) this.#abort = null;
    }
    return !run.cancelled;
  }

  /** Freeze the scene and cut the voice. Resume with resume(). */
  pause() {
    if (this.#paused || !this.#abort) return false;
    this.#paused = true;
    this.classList.add("is-paused");
    this.closest("pinecall-stage")?.silence();
    return true;
  }

  /** Continue from the step that was interrupted. */
  resume() {
    if (!this.#paused) return false;
    this.#paused = false;
    this.classList.remove("is-paused");
    this.#resumers.splice(0).forEach((r) => r());
    return true;
  }

  get paused() {
    return this.#paused;
  }

  /** Stop between steps — the deck calls this when the visitor moves on. */
  cancel() {
    if (this.#abort) this.#abort.cancelled = true;
    // A cancel while paused must release the held play() loop, or it hangs.
    this.#paused = false;
    this.#resumers.splice(0).forEach((r) => r());
  }

  async #step(el, run) {
    const stage = this.closest("pinecall-stage");
    const tag = el.tagName.toLowerCase();

    if (tag === "tts-paragraph") return el.say();

    if (tag === "stage-say") {
      // Speak a line WITHOUT karaoke — used to read a fixed element (a slide
      // title) aloud, optionally in another voice. Text: `say=`, or the text of
      // `from="#id"`, or the element's own content.
      const from = el.getAttribute("from");
      const src = from ? document.querySelector(from) : null;
      const text =
        el.getAttribute("say") || (src?.textContent || el.textContent || "").trim();
      const voice = el.getAttribute("voice") || null;
      if (text && !run.cancelled) await stage.say(null, text, { history: false, voice });
      return this.#hold(Number(el.getAttribute("after") ?? 150), run);
    }

    if (tag === "stage-show") {
      const t = document.querySelector(el.getAttribute("for"));
      t?.classList.add("is-revealed");
      // A reveal is not instant: give the CSS transition its own beat so the
      // sentence that explains the element does not start before it is visible.
      return this.#hold(Number(el.getAttribute("after") ?? 350), run);
    }

    if (tag === "stage-hide") {
      document.querySelector(el.getAttribute("for"))?.classList.remove("is-revealed");
      return;
    }

    if (tag === "stage-line") {
      // Reveal an element WHOLE (not written word by word) and SAY it at the
      // same time — the item pops in and the voice reads it. The spoken text is
      // the `say=` attribute, or the target's own text (a `.txt`/`.body` child
      // if present, so a leading number label is not read aloud).
      const t = document.querySelector(el.getAttribute("for"));
      t?.classList.add("is-revealed");
      const spoken =
        el.getAttribute("say") ||
        t?.querySelector(".txt, .body")?.textContent?.trim() ||
        (t?.textContent || "").trim();
      if (spoken && !run.cancelled) await stage.say(null, spoken, { history: true });
      return this.#hold(Number(el.getAttribute("after") ?? 150), run);
    }

    if (tag === "stage-wait") {
      return this.#hold(Number(el.getAttribute("s") || 1) * 1000, run);
    }

    if (tag === "stage-count") {
      // Spoken, not printed: the page counting down out loud is the whole point.
      const from = Number(el.getAttribute("from") || 3);
      for (let n = from; n >= 1 && !run.cancelled; n--) {
        el.textContent = String(n);
        await stage.say(null, String(n), { history: false });
        await this.#hold(Number(el.getAttribute("gap") ?? 250), run);
      }
      el.textContent = "";
      return;
    }

    if (tag === "stage-ask") {
      // Ask, then LISTEN: the mic goes live for `s` seconds, and if the visitor
      // says nothing the scene simply carries on.
      const text = (el.textContent || "").trim();
      if (text) await stage.say(null, text, { history: true });
      if (run.cancelled) return;
      try {
        await stage.enableMic();
      } catch (e) {
        console.warn("[stage] ask: no mic", e);
      }
      return this.#hold(Number(el.getAttribute("s") || 6) * 1000, run);
    }

    if (tag === "stage-next") {
      this.dispatchEvent(new CustomEvent("stage.scene.next", { bubbles: true }));
      return;
    }
    // Anything else is just markup on the slide — nothing to run.
  }

  /** Sleep that a cancel can cut short. */
  #hold(ms, run) {
    return new Promise((resolve) => {
      const t = setTimeout(resolve, ms);
      const poll = setInterval(() => {
        if (run.cancelled) {
          clearTimeout(t);
          clearInterval(poll);
          resolve();
        }
      }, 60);
      setTimeout(() => clearInterval(poll), ms + 80);
    });
  }
}

/** The microphone: the same session, now listening. */
class PinecallMic extends HTMLElement {
  connectedCallback() {
    this.stage = this.closest("pinecall-stage");
    const b = document.createElement("button");
    b.type = "button";
    b.className = "mic";
    b.textContent = this.getAttribute("label") || "🎙 ask it something";
    b.onclick = async () => {
      b.disabled = true;
      b.textContent = "listening…";
      try {
        await this.stage.enableMic();
        b.textContent = "🎙 mic on — just talk";
      } catch (e) {
        // The button re-arms: the failure modes here (permission denied, a
        // renegotiation that timed out) are all worth a second try.
        b.textContent = `mic failed — ${e?.message ?? "retry"}`;
        b.disabled = false;
        console.warn("[stage] mic", e);
      }
    };
    this.appendChild(b);
  }
}

customElements.define("pinecall-stage", PinecallStage);
customElements.define("tts-paragraph", TtsParagraph);
customElements.define("pinecall-mic", PinecallMic);
customElements.define("stage-scene", StageScene);
// The step elements render nothing and run nothing on their own — the scene
// reads them. Defined so the browser upgrades them (and so a typo'd tag is
// visibly not a step).
for (const t of ["stage-show", "stage-hide", "stage-line", "stage-say", "stage-wait", "stage-count", "stage-ask", "stage-next"]) {
  customElements.define(t, class extends HTMLElement {});
}

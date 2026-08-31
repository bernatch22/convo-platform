/* The fields a supervisor may change between two calls, without a deploy.
 *
 * PUT /pipeline answers with the whole new snapshot, so a save renders the
 * server's own answer instead of a local guess and there is no refetch. A
 * refusal is rendered VERBATIM: the control plane owns the rule, the console
 * only repeats it.
 *
 * The TTS select offers exactly the two models the platform will run. The
 * forbidden ones are shown in the provider panel, struck out, with the same
 * sentence a PUT would have answered with — so nobody discovers the rule by
 * failing.
 *
 * The LLM select is built from `llm.allowed_models`, the server's own list, so
 * the day a third model is priced the console offers it without a redeploy of
 * this file.
 */

import { useState, type FormEvent } from "react";

import { ApiError, putPipeline, type PipelineSnapshot, type PipelineUpdate } from "../lib/api";
import { KNOWN_VOICES } from "../lib/voices";

/** The select value that swaps the dropdown for a free-text ElevenLabs voice id. */
const OTHER = "__other__";

interface ControlsProps {
  snapshot: PipelineSnapshot;
  onSaved: (next: PipelineSnapshot) => void;
}

export function PipelineControls({ snapshot, onSaved }: ControlsProps) {
  const runningModel = snapshot.tts.requested_model ?? snapshot.tts.model;
  const runningLlm = snapshot.llm.requested_model ?? snapshot.llm.model;
  const [voice, setVoice] = useState(snapshot.tts.voice);
  const [model, setModel] = useState(runningModel);
  const [llmModel, setLlmModel] = useState(runningLlm);
  const [greeting, setGreeting] = useState(snapshot.greeting);
  const [sttProvider, setSttProvider] = useState(snapshot.stt.requested_provider);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const chosen = KNOWN_VOICES.find((entry) => entry.id === voice) ?? null;
  const known = chosen !== null;
  const models = [snapshot.tts.default_model, snapshot.tts.latency_model];

  async function save(event: FormEvent) {
    event.preventDefault();
    const update: PipelineUpdate = {};
    if (voice !== snapshot.tts.voice) update.voice = voice;
    if (model !== runningModel) update.tts_model = model;
    if (llmModel !== runningLlm) update.llm_model = llmModel;
    if (greeting !== snapshot.greeting) update.greeting = greeting;
    if (sttProvider !== snapshot.stt.requested_provider) update.stt_provider = sttProvider;

    if (Object.keys(update).length === 0) {
      setSaved(false);
      setError("nothing changed — edit a field before saving");
      return;
    }

    setBusy(true);
    setError(null);
    try {
      onSaved(await putPipeline(snapshot.tenant, snapshot.project, update));
      setSaved(true);
    } catch (cause) {
      setSaved(false);
      setError(cause instanceof ApiError ? cause.detail : String(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="ctl" onSubmit={save}>
      <label className="ctl__field">
        <span className="ctl__label">stt_provider</span>
        <select
          className="ctl__input mono"
          value={sttProvider}
          onChange={(event) => setSttProvider(event.target.value)}
        >
          {snapshot.stt.providers.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
        <p className="ctl__note">
          which ear hears the caller — Soniox <code className="mono">stt-rt-v5</code> or Deepgram
          Flux <code className="mono">flux-general-multi</code>. Anything else is a 422 from the
          control plane; the panel above re-renders with the chosen provider&apos;s own knobs.
        </p>
      </label>

      <label className="ctl__field">
        <span className="ctl__label">voice</span>
        <select
          className="ctl__input"
          value={known ? voice : OTHER}
          onChange={(event) => setVoice(event.target.value === OTHER ? "" : event.target.value)}
        >
          {KNOWN_VOICES.map((entry) => (
            <option key={entry.id} value={entry.id}>
              {entry.name}
            </option>
          ))}
          <option value={OTHER}>another ElevenLabs voice id…</option>
        </select>
        {!known && (
          <input
            className="ctl__input mono"
            value={voice}
            spellCheck={false}
            placeholder="ElevenLabs voice id"
            onChange={(event) => setVoice(event.target.value)}
          />
        )}
        <p className="ctl__note">
          {chosen ? (
            <>
              <span className="mono">{chosen.id}</span> — {chosen.note}
            </>
          ) : (
            "any voice id is accepted; the three named ones are what this account is known to own."
          )}
        </p>
      </label>

      <label className="ctl__field">
        <span className="ctl__label">tts_model</span>
        <select
          className="ctl__input mono"
          value={model}
          onChange={(event) => setModel(event.target.value)}
        >
          {models.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
        <p className="ctl__note">
          only the two the platform runs are offered — {snapshot.tts.forbidden_models.join(" and ")}{" "}
          are refused by the control plane, not hidden by this form.
        </p>
      </label>

      <label className="ctl__field">
        <span className="ctl__label">llm_model</span>
        <select
          className="ctl__input mono"
          value={llmModel}
          onChange={(event) => setLlmModel(event.target.value)}
        >
          {snapshot.llm.allowed_models.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
        <p className="ctl__note">
          the whole menu, read from the control plane — the two models this platform prices and
          measures. They do not cache the same way: see the cache floor in the LLM panel above.
        </p>
      </label>

      <label className="ctl__field ctl__field--wide">
        <span className="ctl__label">greeting</span>
        <textarea
          className="ctl__input ctl__textarea"
          value={greeting}
          rows={3}
          placeholder="empty = the entry stage's prompt opens the call, as it always has"
          onChange={(event) => setGreeting(event.target.value)}
        />
        <p className="ctl__note">
          spoken verbatim as the call opens — <code className="mono">session.say</code>, never
          generated. It applies to the NEXT session.
        </p>
      </label>

      <div className="ctl__foot">
        <button className="ctl__save" type="submit" disabled={busy}>
          {busy ? "saving…" : "save"}
        </button>
        <span className="ctl__banner">
          applies to the NEXT session — a call already running keeps the pipeline it started with.
        </span>
      </div>

      {error && <p className="ctl__error">{error}</p>}
      {saved && !error && (
        <p className="ctl__ok">
          stored. The snapshot above is the control plane&apos;s answer, not a local guess.
        </p>
      )}
    </form>
  );
}

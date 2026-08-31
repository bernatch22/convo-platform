/* The three providers of a voice turn, each as a panel: what hears, what decides, what speaks.
 *
 * Every value comes from GET /pipeline, which reads the platform's own
 * constants and the project's data with the console's overrides already
 * applied — so this screen can never show a pipeline the next call will not
 * run. The prose beside a knob explains what it does; the number is the
 * server's.
 */

import type { ReactNode } from "react";

import type {
  DeepgramEndpointing,
  LlmSnapshot,
  SonioxEndpointing,
  SttSnapshot,
  TtsSnapshot,
} from "../lib/api";
import { voiceName } from "../lib/voices";

/* The ear is a slot: the panel renders the CHOSEN provider's own dials, because
 * Soniox holds a turn open for a silence window and Flux scores its belief that
 * the sentence closed — two different knobs, not one knob under two names. */
export function SttLeg({ stt }: { stt: SttSnapshot }) {
  const soniox = "sensitivity" in stt.endpointing;
  return (
    <Leg role="hears" provider={stt.provider} model={stt.model}>
      <Row k="language hints" v={stt.language_hints.join(" · ")} />
      <Row
        k="sample rate"
        v={`${stt.sample_rate} Hz`}
        note="16 kHz even on PSTN: the provider resamples better than we do"
      />
      {soniox ? (
        <SonioxKnobs endpointing={stt.endpointing as SonioxEndpointing} />
      ) : (
        <FluxKnobs endpointing={stt.endpointing as DeepgramEndpointing} />
      )}
      <Row
        k="keyterms"
        v={stt.keyterms.length ? stt.keyterms.join(", ") : "none"}
        note={
          soniox
            ? "passed as Soniox `context`, not `keyterms` — that argument is silently ignored"
            : "passed as Flux `keyterm`, the argument Soniox ignores"
        }
      />
      <Row
        k="switchable to"
        v={stt.providers.filter((name) => name !== stt.provider).join(", ") || "nothing else"}
        note="the ear is project data, changed from Control below and effective on the NEXT session"
      />
    </Leg>
  );
}

function SonioxKnobs({ endpointing }: { endpointing: SonioxEndpointing }) {
  return (
    <>
      <Row
        k="max endpoint delay"
        v={`${endpointing.max_endpoint_delay_ms} ms`}
        note="the longest Soniox will hold a turn open waiting for more speech"
      />
      <Row
        k="latency level"
        v={String(endpointing.latency_adjustment_level)}
        note="how much semantic endpointing may trade silence for certainty — higher waits longer to be surer the sentence ended"
      />
      <Row
        k="sensitivity"
        v={String(endpointing.sensitivity)}
        note="how eagerly a pause is read as the end of a turn; low means the caller may think aloud"
      />
    </>
  );
}

function FluxKnobs({ endpointing }: { endpointing: DeepgramEndpointing }) {
  return (
    <>
      <Row
        k="eot threshold"
        v={String(endpointing.eot_threshold)}
        note="how sure Flux must be that the sentence closed before it ends the turn — the model scores it, no silence timer decides"
      />
      <Row
        k="eot timeout"
        v={`${endpointing.eot_timeout_ms} ms`}
        note="the hard stop when the score never gets there, matching Soniox's max endpoint delay"
      />
      <Row
        k="eager eot"
        v={endpointing.eager_eot_threshold === null ? "off" : String(endpointing.eager_eot_threshold)}
        note="Flux's preemptive hook: off by decision, generation waits for the confirmed end of turn"
      />
    </>
  );
}

export function LlmLeg({ llm }: { llm: LlmSnapshot }) {
  return (
    <Leg role="decides" provider={llm.provider} model={llm.model}>
      <Row k="caching" v={llm.caching ?? "off"} />
      <Row k="cache floor" v={`${llm.cache_minimum_tokens} tokens`} note={llm.cache_note} />
      <Row k="max tokens" v={String(llm.max_tokens)} note="the ceiling on one spoken answer" />
    </Leg>
  );
}

export function TtsLeg({ tts }: { tts: TtsSnapshot }) {
  const named = voiceName(tts.voice);
  return (
    <Leg role="speaks" provider={tts.provider} model={tts.model}>
      <Row
        k="requested"
        v={tts.requested_model ?? `— (platform default: ${tts.default_model})`}
        note={
          tts.requested_model
            ? "what the project asked for; the model above is what the platform will really run"
            : "the project names no model, so the default runs"
        }
      />
      <Row k="latency profile" v={tts.latency_model} note="the model a project may opt into when it wants speed over expression" />
      <Row
        k="voice"
        v={named ? `${named} · ${tts.voice}` : tts.voice}
        note={named ? "an account voice this console knows by name" : "a voice id this console has no name for"}
      />
      <Row k="sync alignment" v={tts.sync_alignment ? "on" : "off"} note="timed words, so the event log and the karaoke know when each word was spoken" />

      <div className="leg__refused">
        <span className="leg__refused-title">never run</span>
        {tts.forbidden_models.map((model) => (
          <p key={model} className="leg__refused-row">
            <s className="mono">{model}</s>
            <span className="leg__refused-why">{tts.forbidden_reasons[model] ?? "refused by the platform"}</span>
          </p>
        ))}
      </div>
    </Leg>
  );
}

interface LegProps {
  role: string;
  provider: string;
  model: string;
  children: ReactNode;
}

function Leg({ role, provider, model, children }: LegProps) {
  return (
    <article className="panel leg">
      <div className="panel__head">
        <span className="panel__title">{provider}</span>
        <span className="badge">{role}</span>
      </div>
      <div className="panel__body">
        <div className="leg__model mono">{model}</div>
        <dl className="leg__rows">{children}</dl>
      </div>
    </article>
  );
}

function Row({ k, v, note }: { k: string; v: string; note?: string }) {
  return (
    <div className="leg__row">
      <dt className="leg__k">{k}</dt>
      <dd className="leg__v mono">{v}</dd>
      {note && <p className="leg__note">{note}</p>}
    </div>
  );
}

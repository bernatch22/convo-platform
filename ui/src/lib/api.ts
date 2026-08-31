/* The only file that knows the control plane exists.
 *
 * Every type here is transcribed from a route docstring in api.py, which is
 * where the shapes are defined — field for field, including the ones this
 * shell does not render yet, so a later card fills a screen instead of
 * inventing a contract.
 *
 * In dev, vite proxies these paths to the control plane (see vite.config.ts).
 * In production api.py serves this bundle itself, so relative paths are right
 * in both worlds and there is no base URL to configure.
 */

/* ── /tenants ─────────────────────────────────────────────────────────────── */

/** One project of one tenant: a business process the fleet can run. */
export interface Project {
  id: string;
  name: string;
  voice: string;
  language: string;
}

/** One business this deploy serves, with the projects it can route to. */
export interface Tenant {
  tenant: string;
  projects: Project[];
}

/* ── /token and /observe ──────────────────────────────────────────────────── */

export type Channel = "voice" | "chat";

/** What a client must say to open a session. */
export interface TokenRequest {
  tenant: string;
  project: string;
  channel: Channel;
  user_id?: string;
}

/** One caller's ticket into one fresh room, with the agent dispatch inside the JWT. */
export interface SessionTicket {
  url: string;
  room: string;
  token: string;
}

/** A listen-only ticket: receives audio and transcription, publishes nothing, stays hidden. */
export interface ObserverTicket {
  url: string;
  room: string;
  identity: string;
  token: string;
}

/* ── /sessions ────────────────────────────────────────────────────────────── */

/** One line of the call log. `outcome` and `cost_eur` are null while the call runs.
 *
 * `phone` is the caller's number off `session.start`, and null when the
 * session never came in over the telephone: `channel` says "voice" for a
 * browser call and a PSTN call alike, so this is the only field that tells
 * the two apart in the log.
 */
export interface SessionLine {
  id: string;
  tenant: string;
  project: string;
  channel: Channel;
  started_at: number;
  ended_at: number | null;
  outcome: string | null;
  events: number;
  turns: number;
  cost_eur: number | null;
  phone: string | null;
}

/** One fact in the append-only log. A turn's latencies live in `payload.metrics`. */
export interface SessionEvent {
  seq: number;
  t_ms: number;
  kind: string;
  payload: Record<string, unknown>;
}

/** One session in full: its list line, the end-of-call report, every event in seq order. */
export interface SessionView extends SessionLine {
  report: Record<string, unknown> | null;
  events_log: SessionEvent[];
}

/** The raw body of GET /sessions/{id} — `events` is the array here, not the count. */
type SessionViewBody = Omit<SessionLine, "events"> & {
  events: SessionEvent[];
  report: Record<string, unknown> | null;
};

/* ── /sessions/{id}/live (SSE) ────────────────────────────────────────────── */

/** The four frames the live log emits, in the order a reader meets them. */
export type LiveFrame =
  | { type: "open"; session: SessionLine }
  | { type: "append"; event: SessionEvent }
  | { type: "end"; seq: number; outcome: string | null }
  | { type: "error"; error: string };

/* ── /live-calls ──────────────────────────────────────────────────────────── */

/** A call happening right now, as the SFU sees it. A phone call never passed through /token. */
export interface LiveCall {
  room: string;
  sid: string;
  participants: number;
  started_at: number;
  agent: boolean;
  identities: string[];
  phone: string | null;
  session_id: string | null;
  tenant: string | null;
  project: string | null;
}

/* ── /pipeline ────────────────────────────────────────────────────────────── */

/** Soniox as the next session will run it, endpointing knobs included. */
export interface SttSnapshot {
  provider: string;
  model: string;
  language_hints: string[];
  sample_rate: number;
  endpointing: {
    max_endpoint_delay_ms: number;
    latency_adjustment_level: number;
    sensitivity: number;
  };
  keyterms: string[];
}

/** The LLM leg, with the cache floor that makes caching a no-op below it. */
export interface LlmSnapshot {
  /** The family, not a vendor hostname: "anthropic" or "openai". */
  provider: string;
  model: string;
  /** What the project asked for; null means it takes the platform default. */
  requested_model: string | null;
  default_model: string;
  /** Exactly the models the control plane will accept; anything else is a 422. */
  allowed_models: string[];
  caching: string | null;
  max_tokens: number;
  cache_minimum_tokens: number;
  cache_note: string;
}

/** The TTS leg: what was asked for, what runs, and what the platform refuses to run. */
export interface TtsSnapshot {
  provider: string;
  model: string;
  requested_model: string | null;
  default_model: string;
  latency_model: string;
  forbidden_models: string[];
  /** model id -> the sentence the control plane refuses it with, verbatim. */
  forbidden_reasons: Record<string, string>;
  voice: string;
  sync_alignment: boolean;
}

/** One field the console changed, and when. */
export interface PipelineOverrideRow {
  field: string;
  value: string;
  updated_at: number;
}

/** Medians in SECONDS over stored voice sessions; a never-measured one is null, never 0. */
export interface LatencyMedians {
  transcription_delay: number | null;
  end_of_turn_delay: number | null;
  llm_node_ttft: number | null;
  tts_node_ttfb: number | null;
  e2e_latency: number | null;
}

/** Everything the pipeline screen reads: the three legs, the overrides, the measurements. */
export interface PipelineSnapshot {
  tenant: string;
  project: string;
  name: string;
  language: string;
  greeting: string;
  stt: SttSnapshot;
  llm: LlmSnapshot;
  tts: TtsSnapshot;
  overrides: PipelineOverrideRow[];
  overridable: string[];
  latency: {
    sessions: number;
    turns: number;
    medians: LatencyMedians;
  };
}

/** The three fields a supervisor may change between calls; anything else is a 422. */
export interface PipelineUpdate {
  voice?: string;
  tts_model?: string;
  greeting?: string;
  llm_model?: string;
}

/* ── errors ───────────────────────────────────────────────────────────────── */

/** A control-plane refusal with the status and the sentence the API gave, for the UI to show. */
export class ApiError extends Error {
  readonly status: number;

  readonly detail: string;

  constructor(status: number, detail: string) {
    super(`${status} ${detail}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/* ── the calls ────────────────────────────────────────────────────────────── */

/** Every routable tenant and its projects — the switcher's only source of truth. */
export async function listTenants(signal?: AbortSignal): Promise<Tenant[]> {
  return request<Tenant[]>("/tenants", signal ? { signal } : {});
}

/** Mint a session ticket: a fresh room joinable by exactly this caller. */
export async function mintToken(req: TokenRequest): Promise<SessionTicket> {
  return request<SessionTicket>("/token", json("POST", req));
}

/** Mint a hidden, listen-only ticket into a room somebody else is already in. */
export async function observe(room: string): Promise<ObserverTicket> {
  return request<ObserverTicket>("/observe", json("POST", { room }));
}

/** The call log, newest first, optionally narrowed to one tenant or project. */
export async function listSessions(
  params: { tenant?: string; project?: string; limit?: number } = {},
  signal?: AbortSignal,
): Promise<SessionLine[]> {
  return request<SessionLine[]>(`/sessions${query(params)}`, signal ? { signal } : {});
}

/** One session in full. `events` is split into the count and the log so both keep their names. */
export async function getSession(id: string, signal?: AbortSignal): Promise<SessionView> {
  const body = await request<SessionViewBody>(
    `/sessions/${encodeURIComponent(id)}`,
    signal ? { signal } : {},
  );
  const { events, ...line } = body;
  return { ...line, events: events.length, events_log: events };
}

/** Calls in progress on the SFU, phone calls included. Throws ApiError(503) when it is down. */
export async function listLiveCalls(signal?: AbortSignal): Promise<LiveCall[]> {
  return request<LiveCall[]>("/live-calls", signal ? { signal } : {});
}

/** The pipeline the NEXT session of this project will run on, overrides already applied. */
export async function getPipeline(
  tenant: string,
  project: string,
  signal?: AbortSignal,
): Promise<PipelineSnapshot> {
  return request<PipelineSnapshot>(pipelinePath(tenant, project), signal ? { signal } : {});
}

/** Change an overridable pipeline field for the next session; the answer is the new snapshot. */
export async function putPipeline(
  tenant: string,
  project: string,
  update: PipelineUpdate,
): Promise<PipelineSnapshot> {
  return request<PipelineSnapshot>(pipelinePath(tenant, project), json("PUT", update));
}

/** Follow one session's log as it appends, from the last seq seen. Returns the unsubscribe. */
export function watchSession(
  id: string,
  after: number,
  onFrame: (frame: LiveFrame) => void,
): () => void {
  const source = new EventSource(`/sessions/${encodeURIComponent(id)}/live?after=${after}`);

  source.addEventListener("open", (event) => {
    // EventSource fires its OWN "open" when the socket connects, and it collides with
    // the server's `event: open` frame. The native one carries no data; only the frame
    // does, so the data is what tells them apart.
    const data = (event as MessageEvent<string>).data;
    if (typeof data !== "string") return;
    onFrame({ type: "open", session: JSON.parse(data) as SessionLine });
  });
  source.addEventListener("append", (event) => {
    onFrame({ type: "append", event: parse<SessionEvent>(event) });
  });
  source.addEventListener("end", (event) => {
    const { seq, outcome } = parse<{ seq: number; outcome: string | null }>(event);
    onFrame({ type: "end", seq, outcome });
    source.close();
  });
  source.addEventListener("error", (event) => {
    onFrame({ type: "error", error: describe(event) });
  });

  return () => source.close();
}

/** Is the control plane answering? Used by the rail's connection dot; never throws. */
export async function probe(signal?: AbortSignal): Promise<{ up: boolean; ms: number }> {
  const started = performance.now();
  try {
    const response = await fetch("/tenants", signal ? { signal } : {});
    return { up: response.ok, ms: Math.round(performance.now() - started) };
  } catch {
    return { up: false, ms: Math.round(performance.now() - started) };
  }
}

function pipelinePath(tenant: string, project: string): string {
  return `/pipeline/${encodeURIComponent(tenant)}/${encodeURIComponent(project)}`;
}

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) search.set(key, String(value));
  }
  return search.toString() ? `?${search}` : "";
}

function json(method: string, body: unknown): RequestInit {
  return { method, headers: { "content-type": "application/json" }, body: JSON.stringify(body) };
}

function parse<T>(event: Event): T {
  return JSON.parse((event as MessageEvent<string>).data) as T;
}

function describe(event: Event): string {
  const data = (event as MessageEvent<string>).data;
  return typeof data === "string" ? data : "the live stream closed";
}

async function request<T>(path: string, init: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    throw new ApiError(response.status, await detailOf(response));
  }
  return (await response.json()) as T;
}

async function detailOf(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    return typeof body.detail === "string" ? body.detail : response.statusText;
  } catch {
    return response.statusText;
  }
}

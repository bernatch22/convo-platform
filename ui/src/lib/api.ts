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

/** What a supervisor asked to be allowed to do in a live room. The token is the answer. */
export type SupervisorCapability = "listen" | "whisper" | "takeover";

/** One supervisor's short-lived ticket into one live call. `identity` is always `sup:<uid>`. */
export interface SupervisorTicket {
  url: string;
  room: string;
  identity: string;
  capability: SupervisorCapability;
  token: string;
}

/** What the SFU says about a supervisor who is already in the room — not what the ticket said.
 *
 * `hidden` is the server's own word for "the caller cannot see this
 * participant": it is the proof the desk puts on screen, and it comes from
 * `list_participants`, never from this client. `announced` is whether the
 * room's agent was told, which is what puts `supervisor.join` in the log.
 */
export interface SupervisorPresence {
  identity: string;
  capability: SupervisorCapability;
  hidden: boolean;
  announced: boolean;
}

/* ── /sessions ────────────────────────────────────────────────────────────── */

/** One question ring 4 asked of a finished call. `passed: null` = nothing here to check.
 *
 * `score` is present only on the judged check and is its raw 0-1; a check code
 * decided has no number, because consent either happened or it did not.
 */
export interface ScoreCheck {
  name: string;
  kind: "deterministic" | "judge";
  passed: boolean | null;
  score?: number;
  reason: string;
}

/** What the one LLM call did, or the sentence saying why it was never made. */
export interface JudgeRun {
  ran: boolean;
  skipped: string | null;
  model: string;
  threshold: number;
  cap_eur: number;
  cost_eur: number;
}

/** The payload of a session's `session.score` event: the verdict and everything behind it. */
export interface SessionScore {
  version: number;
  score: number;
  verdict: "pass" | "fail";
  failed: string[];
  turns: number;
  checks: ScoreCheck[];
  judge: JudgeRun | null;
}

/** One line of the call log. `outcome` and `cost_eur` are null while the call runs.
 *
 * `phone` is the caller's number off `session.start`, and null when the
 * session never came in over the telephone: `channel` says "voice" for a
 * browser call and a PSTN call alike, so this is the only field that tells
 * the two apart in the log.
 *
 * `score` is null in three different situations and none of them is a bad
 * call: not scored yet, too short to judge, or a project that opted out. The
 * screen shows a dash, never a zero.
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
  score: SessionScore | null;
  /** Whether this call left an OGG the console can play — a look on disk, not in the log. */
  audio: boolean;
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
export interface SonioxEndpointing {
  max_endpoint_delay_ms: number;
  latency_adjustment_level: number;
  sensitivity: number;
}

export interface DeepgramEndpointing {
  eot_threshold: number;
  eot_timeout_ms: number;
  eager_eot_threshold: number | null;
}

export interface SttSnapshot {
  /** The provider that will really run — an unknown `requested_provider` falls back to soniox. */
  provider: string;
  requested_provider: string;
  providers: string[];
  model: string;
  language_hints: string[];
  sample_rate: number;
  /** The CHOSEN provider's own dials: Soniox holds a silence window, Flux scores a turn. */
  endpointing: SonioxEndpointing | DeepgramEndpointing;
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

/** One phone line that reaches this project; `serving` is false on another fleet's number. */
export interface PhoneLine {
  number: string;
  fleet: string;
  channel: string;
  serving: boolean;
}

/** The project's own telephony: its lines, and the sentence the screen prints under them. */
export interface PhoneSnapshot {
  /** The agent_name this deploy dispatches to — the fleet a line has to be on to be answered. */
  fleet: string;
  /** Empty for a project nobody can call: a number is a route, not a property of a project. */
  lines: PhoneLine[];
  note: string;
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
  phone: PhoneSnapshot;
  overrides: PipelineOverrideRow[];
  overridable: string[];
  latency: {
    sessions: number;
    turns: number;
    medians: LatencyMedians;
  };
}

/** The fields a supervisor may change between calls; anything else is a 422. */
export interface PipelineUpdate {
  voice?: string;
  tts_model?: string;
  greeting?: string;
  stt_provider?: string;
  llm_model?: string;
}

/* ── /evals ───────────────────────────────────────────────────────────────── */

/** One metric's verdict over a whole run, and what it gained or lost since the last one. */
export interface MetricScore {
  metric: string;
  /** Mean over the run's cases, 0..1. */
  score: number;
  passed: number;
  failed: number;
  /** This score minus the previous run's of the same suite; null when there was no previous. */
  delta: number | null;
}

export type EvalStatus = "running" | "done" | "failed";

/** One `deepeval` run of one project's suite: what it scored and where its evidence is. */
export interface EvalRun {
  id: string;
  tenant: string;
  project: string;
  suite: string;
  status: EvalStatus;
  started_at: number;
  finished_at: number | null;
  git_sha: string | null;
  milestone: string | null;
  report_html: string | null;
  log_path: string | null;
  detail: string | null;
  metrics: MetricScore[];
  /** The run this one is diffed against, or null when it is the first of its suite. */
  previous: string | null;
}

/** A run being polled: the same line, plus the tail of what the subprocess is writing. */
export interface EvalRunStatus extends EvalRun {
  log: string[];
  /** Is the box still holding its single eval slot? */
  busy: boolean;
}

/** What one project can be asked to run. The suite ids are the project's own data. */
export interface ProjectSuites {
  tenant: string;
  project: string;
  name: string;
  suites: string[];
}

/** What the console must name before the box spends minutes of paid LLM traffic. */
export interface EvalRunRequest {
  tenant: string;
  project: string;
  suite: string;
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

/** Mint a supervisor's short-lived, role-scoped ticket into one live room. */
export async function supervise(
  room: string,
  capability: SupervisorCapability = "listen",
  userId = "",
): Promise<SupervisorTicket> {
  return request<SupervisorTicket>(
    "/supervise",
    json("POST", { room, capability, user_id: userId }),
  );
}

/** Tell the control plane the supervisor is through the door, and get the SFU's own view back. */
export async function superviseEntered(
  room: string,
  identity: string,
): Promise<SupervisorPresence> {
  return request<SupervisorPresence>("/supervise/entered", json("POST", { room, identity }));
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

/** Where this session's recording is served from — an `<audio src>`, never a fetch.
 *
 * The control plane composes the path from the session id on its side; nothing
 * here knows where an OGG lives on the box, which is the point. A session whose
 * `audio` is false has no such file and the screen must not ask for one.
 */
export function recordingUrl(id: string): string {
  return `/sessions/${encodeURIComponent(id)}/recording`;
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

/** Every routable project and the eval suites it declares — the Run buttons' only source. */
export async function listEvalSuites(signal?: AbortSignal): Promise<ProjectSuites[]> {
  return request<ProjectSuites[]>("/evals/suites", signal ? { signal } : {});
}

/** Stored eval runs, newest first, each already diffed against the previous run of its suite. */
export async function listEvalRuns(
  params: { tenant?: string; project?: string; suite?: string; limit?: number } = {},
  signal?: AbortSignal,
): Promise<EvalRun[]> {
  return request<EvalRun[]>(`/evals/runs${query(params)}`, signal ? { signal } : {});
}

/** Spend money: run one project's suite on the box. Throws ApiError(409) while one is going. */
export async function launchEvalRun(req: EvalRunRequest): Promise<EvalRun> {
  return request<EvalRun>("/evals/run", json("POST", req));
}

/** One run's standing while it happens, with the tail of its log. */
export async function getEvalRun(id: string, signal?: AbortSignal): Promise<EvalRunStatus> {
  return request<EvalRunStatus>(`/evals/run/${encodeURIComponent(id)}`, signal ? { signal } : {});
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

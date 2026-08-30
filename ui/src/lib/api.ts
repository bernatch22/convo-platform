/* The only file that knows the control plane exists.
 *
 * Everything the UI reads or writes goes through here, typed once. Two of these
 * endpoints (`/tenants`, `/token`) are live on master today; the rest are the
 * read side and the pipeline API being built alongside this shell (card
 * tk-667be6) — their types are written from that card's spec so the day they
 * land the diff is a deletion of the "not built yet" guards, nothing more.
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

/* ── /token ───────────────────────────────────────────────────────────────── */

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

/* ── /sessions ────────────────────────────────────────────────────────────── */

/** One row of the call log: what the store knows about a session besides its events. */
export interface SessionRow {
  id: string;
  tenant: string;
  project: string;
  channel: Channel;
  started: number;
  ended: number | null;
  outcome: string | null;
  cost: number | null;
  turns: number;
}

/** One line of the append-only log: numbered, timed, never edited. */
export interface SessionEvent {
  seq: number;
  kind: string;
  t_ms: number;
  payload: Record<string, unknown>;
}

/** A finished session in full: its row, every event in seq order, and the framework's report. */
export interface SessionDetail {
  session: SessionRow;
  events: SessionEvent[];
  report: Record<string, unknown> | null;
}

/* ── /pipeline ────────────────────────────────────────────────────────────── */

/** Soniox as configured for this project — model plus the endpointing knobs. */
export interface SttConfig {
  provider: string;
  model: string;
  language_hints: string[];
  endpointing: Record<string, number>;
  context: string | null;
}

/** The LLM leg: model id and whether the prefix is being cached. */
export interface LlmConfig {
  provider: string;
  model: string;
  caching: string | null;
}

/** The TTS leg: model chosen by tts_model(), the project's voice, alignment. */
export interface TtsConfig {
  provider: string;
  model: string;
  voice: string;
  sync_alignment: boolean;
}

/** Measured medians over the last N stored voice sessions of this project, in ms. */
export interface PipelineLatencies {
  ttft_ms: number | null;
  e2e_ms: number | null;
  eot_ms: number | null;
  transcription_delay_ms: number | null;
  sessions: number;
}

/** The three providers as data, plus what an operator may change without a deploy. */
export interface Pipeline {
  tenant: string;
  project: string;
  stt: SttConfig;
  llm: LlmConfig;
  tts: TtsConfig;
  greeting: string;
  language: string;
  latencies: PipelineLatencies;
}

/** The three fields an operator may override per project; absent means "leave it". */
export interface PipelineOverride {
  voice?: string;
  tts_model?: string;
  greeting?: string;
}

/* ── errors ───────────────────────────────────────────────────────────────── */

/** A control-plane failure with the status and the detail the API gave, for the UI to show. */
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
  return request<SessionTicket>("/token", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(req),
  });
}

/** The call log, newest first, optionally narrowed to one tenant. */
export async function listSessions(
  params: { tenant?: string; limit?: number } = {},
  signal?: AbortSignal,
): Promise<SessionRow[]> {
  const query = new URLSearchParams();
  if (params.tenant) query.set("tenant", params.tenant);
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  const suffix = query.toString() ? `?${query}` : "";
  return request<SessionRow[]>(`/sessions${suffix}`, signal ? { signal } : {});
}

/** One session in full: row, events in seq order, session report. */
export async function getSession(id: string, signal?: AbortSignal): Promise<SessionDetail> {
  return request<SessionDetail>(`/sessions/${encodeURIComponent(id)}`, signal ? { signal } : {});
}

/** Subscribe to a live session's events as they append. Returns the unsubscribe. */
export function watchSession(id: string, onEvent: (event: SessionEvent) => void): () => void {
  const source = new EventSource(`/sessions/${encodeURIComponent(id)}/live`);
  source.onmessage = (message: MessageEvent<string>) => {
    onEvent(JSON.parse(message.data) as SessionEvent);
  };
  return () => source.close();
}

/** The three providers this project runs on, with their measured latencies. */
export async function getPipeline(
  tenant: string,
  project: string,
  signal?: AbortSignal,
): Promise<Pipeline> {
  const path = `/pipeline/${encodeURIComponent(tenant)}/${encodeURIComponent(project)}`;
  return request<Pipeline>(path, signal ? { signal } : {});
}

/** Change voice / tts_model / greeting for the next session — no deploy, no restart. */
export async function putPipeline(
  tenant: string,
  project: string,
  override: PipelineOverride,
): Promise<Pipeline> {
  const path = `/pipeline/${encodeURIComponent(tenant)}/${encodeURIComponent(project)}`;
  return request<Pipeline>(path, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(override),
  });
}

/** Is the control plane answering? Used by the rail's connection dot, never throws. */
export async function probe(signal?: AbortSignal): Promise<{ up: boolean; ms: number }> {
  const started = performance.now();
  try {
    const response = await fetch("/tenants", signal ? { signal } : {});
    return { up: response.ok, ms: Math.round(performance.now() - started) };
  } catch {
    return { up: false, ms: Math.round(performance.now() - started) };
  }
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

/* One live session, raw livekit-client: the door, the microphone, the words, the state.
 *
 * Four doors, one hook. `voice` and `chat` mint a ticket at POST /token and
 * open a fresh room the agent is dispatched into; `observe` and `supervise`
 * join a room somebody is already in — a phone call, usually, which never
 * passed through /token at all. After connect all four are the same object:
 * the same `lk.transcription` streams, the same `lk.agent.state` attribute,
 * the same transcript on screen.
 *
 * `observe` and `supervise` differ only in who is knocking. /observe mints an
 * anonymous `observer:<hex>` ticket — a developer peeking at a room from the
 * tenant screen. /supervise mints a named, short-lived, role-scoped
 * `sup:<uid>` one, and the supervisor desk is expected to follow it with
 * `superviseEntered` so the arrival reaches the caller's log. Both are hidden
 * and publish nothing; only one of them is on the record.
 *
 * Deliberately not here: no components package, no audio element in JSX, no
 * global store. The Room is a ref because it is not React state — what React
 * renders is what the room told us.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { Room, RoomEvent, Track, type Participant, type TextStreamReader } from "livekit-client";

import {
  mintToken,
  observe,
  supervise,
  type Channel,
  type SupervisorCapability,
} from "./api";
import {
  AGENT_STATE,
  SEGMENT_ID,
  TRANSCRIPTION_FINAL,
  agentState,
  upsert,
  type AgentState,
  type Line,
  type Speaker,
} from "./transcript";
import { aim, isAgent } from "./verbs";

const TRANSCRIPTION_TOPIC = "lk.transcription";
const CHAT_TOPIC = "lk.chat";

/** Which door this session came in by. `observe` publishes nothing; `supervise` depends. */
export type Mode = Channel | "observe" | "supervise";

/** Who is knocking and with which powers — the only thing a supervisor's ticket varies.
 *
 * `userId` is deliberately stable for the life of a desk: LiveKit admits one
 * connection per identity, so re-minting `sup:<userId>` with a bigger grant
 * UPGRADES the participant already in the room instead of adding a second
 * ghost of the same person. Leave it empty and every escalation is a stranger.
 */
export interface Ticketed {
  capability: SupervisorCapability;
  userId: string;
}

/** Where the session is. `ended` is a call that finished; `failed` is one that never opened. */
export type Phase = "idle" | "connecting" | "live" | "ended" | "failed";

/** Everything a screen needs to render one conversation, and the four verbs that drive it. */
export interface Live {
  mode: Mode | null;
  phase: Phase;
  error: string | null;
  room: string | null;
  identity: string | null;
  lines: Line[];
  state: AgentState | null;
  audible: boolean;
  capability: SupervisorCapability | null;
  open: (mode: Mode, room?: string, as?: Ticketed) => Promise<void>;
  close: () => Promise<void>;
  say: (text: string) => Promise<void>;
  listen: (on: boolean) => void;
  mic: (on: boolean) => Promise<void>;
  verb: (kind: string, body?: Record<string, unknown>) => Promise<Record<string, unknown>>;
}

/** Open, hold and close one session against this tenant's project. */
export function useRoom(tenant: string, project: string): Live {
  const room = useRef<Room | null>(null);
  const speakers = useRef<HTMLMediaElement[]>([]);
  const audibleRef = useRef(true);
  const typed = useRef(0);

  const joined = useRef<string | null>(null);

  const [mode, setMode] = useState<Mode | null>(null);
  const [capability, setCapability] = useState<SupervisorCapability | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState<string | null>(null);
  const [identity, setIdentity] = useState<string | null>(null);
  const [lines, setLines] = useState<Line[]>([]);
  const [state, setState] = useState<AgentState | null>(null);
  const [audible, setAudible] = useState(true);

  const close = useCallback(async () => {
    const open = room.current;
    room.current = null;
    speakers.current.forEach((element) => element.remove());
    speakers.current = [];
    if (open) await open.disconnect();
    joined.current = null;
    setPhase((was) => (was === "idle" || was === "failed" ? was : "ended"));
    setState(null);
    setIdentity(null);
  }, []);

  const open = useCallback(
    async (next: Mode, target?: string, as?: Ticketed) => {
      // Re-entering the SAME room with a bigger ticket is an escalation, not a
      // new call: the transcript on screen is the one the supervisor has been
      // reading and throwing it away would hide what they are about to act on.
      const escalating = Boolean(target) && target === joined.current;
      await close();
      setMode(next);
      setPhase("connecting");
      setError(null);
      if (!escalating) setLines([]);
      setName(target ?? null);
      setIdentity(null);
      setCapability(null);
      // A watched call starts SILENT: a supervisor reads it by default and only
      // then chooses to hear it. `startAudio` is still called — it needs the
      // click that opened the door — so the toggle has something to unmute.
      if (!escalating) {
        const listen = next === "voice" || next === "chat";
        audibleRef.current = listen;
        setAudible(listen);
      }
      try {
        const ticket = await ticketFor(next, target ?? "", tenant, project, as);
        const live = new Room({ adaptiveStream: false, dynacast: false });
        wire(live, { setLines, setState, speakers, audibleRef });
        room.current = live;
        await live.connect(ticket.url, ticket.token);
        if (next === "voice") await live.localParticipant.setMicrophoneEnabled(true);
        await live.startAudio();
        setName(ticket.room);
        joined.current = ticket.room;
        setIdentity(live.localParticipant.identity);
        setCapability(as?.capability ?? null);
        setPhase("live");
      } catch (cause) {
        room.current = null;
        setError(cause instanceof Error ? cause.message : String(cause));
        setPhase("failed");
      }
    },
    [close, project, tenant],
  );

  const say = useCallback(async (text: string) => {
    const open = room.current;
    const said = text.trim();
    if (!open || !said) return;
    // Verified against the running stack: a typed message is NOT echoed back on
    // lk.transcription — there is no STT in a chat session to transcribe it. The
    // caller's own line exists on screen only because this puts it there.
    typed.current += 1;
    const id = `typed-${typed.current}`;
    setLines((lines) => upsert(lines, { id, speaker: "user", text: said, final: true }));
    await open.localParticipant.sendText(said, { topic: CHAT_TOPIC });
  }, []);

  /** The supervisor's own microphone — the half of a takeover the caller actually hears. */
  const mic = useCallback(async (on: boolean) => {
    const open = room.current;
    if (!open) return;
    await open.localParticipant.setMicrophoneEnabled(on);
  }, []);

  /** Aim one supervision verb at this room's agent — `core/lib/verbs` owns the protocol. */
  const verb = useCallback(async (kind: string, body: Record<string, unknown> = {}) => {
    const open = room.current;
    if (!open) throw new Error("not in a room");
    return aim(open, kind, body);
  }, []);

  const listen = useCallback((on: boolean) => {
    audibleRef.current = on;
    speakers.current.forEach((element) => {
      element.muted = !on;
    });
    setAudible(on);
  }, []);

  useEffect(() => () => void close(), [close]);

  return {
    mode,
    phase,
    error,
    room: name,
    identity,
    lines,
    state,
    audible,
    capability,
    open,
    close,
    say,
    listen,
    mic,
    verb,
  };
}

/** The ticket each door is opened with — the only line where the four differ. */
async function ticketFor(
  mode: Mode,
  target: string,
  tenant: string,
  project: string,
  as?: Ticketed,
): Promise<{ url: string; token: string; room: string }> {
  if (mode === "supervise") return supervise(target, as?.capability ?? "listen", as?.userId ?? "");
  if (mode === "observe") return observe(target);
  return mintToken({ tenant, project, channel: mode });
}

interface Sinks {
  setLines: (update: (lines: Line[]) => Line[]) => void;
  setState: (state: AgentState | null) => void;
  speakers: { current: HTMLMediaElement[] };
  audibleRef: { current: boolean };
}

/** Subscribe to everything this screen renders, BEFORE connect — a late handler misses words. */
function wire(room: Room, sinks: Sinks): void {
  room.registerTextStreamHandler(TRANSCRIPTION_TOPIC, (reader, from) => {
    void read(room, reader, from.identity, sinks.setLines);
  });

  room.on(RoomEvent.ParticipantConnected, (participant) => {
    const state = stateOf(participant);
    if (state) sinks.setState(state);
  });
  room.on(RoomEvent.ParticipantAttributesChanged, (changed, participant) => {
    if (AGENT_STATE in changed && isAgent(participant)) {
      sinks.setState(agentState(changed[AGENT_STATE]));
    }
  });
  // The agent's voice, and the caller's when observing. The element lives in the
  // document (a detached one is at the mercy of the browser's autoplay rules) but
  // never on screen: audio is not a widget, it is the call.
  room.on(RoomEvent.TrackSubscribed, (track) => {
    if (track.kind !== Track.Kind.Audio) return;
    const element = track.attach();
    element.muted = !sinks.audibleRef.current;
    element.style.display = "none";
    document.body.appendChild(element);
    sinks.speakers.current.push(element);
  });
}

/** One transcription segment, from its first delta to the trailer that settles it. */
async function read(
  room: Room,
  reader: TextStreamReader,
  identity: string,
  setLines: Sinks["setLines"],
): Promise<void> {
  const id = reader.info.attributes?.[SEGMENT_ID] ?? reader.info.id;
  const speaker = speakerOf(room, identity);
  let text = "";
  for await (const chunk of reader) {
    text += chunk;
    setLines((lines) => upsert(lines, { id, speaker, text, final: false }));
  }
  // Only now does `attributes` carry the trailer: during the loop it always says "false".
  const final = reader.info.attributes?.[TRANSCRIPTION_FINAL] === "true";
  setLines((lines) => upsert(lines, { id, speaker, text, final }));
}

/** Who is speaking, by participant identity — never by track id, which chat mode does not have. */
function speakerOf(room: Room, identity: string): Speaker {
  const participant = room.remoteParticipants.get(identity);
  return participant && isAgent(participant) ? "agent" : "user";
}

function stateOf(participant: Participant): AgentState | null {
  return isAgent(participant) ? agentState(participant.attributes[AGENT_STATE]) : null;
}

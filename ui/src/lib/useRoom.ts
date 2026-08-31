/* One live session, raw livekit-client: the door, the microphone, the words, the state.
 *
 * Three doors, one hook. `voice` and `chat` mint a ticket at POST /token and
 * open a fresh room the agent is dispatched into; `observe` mints a hidden,
 * publish-nothing ticket at POST /observe and joins a room somebody is
 * already in — a phone call, usually, which never passed through /token at
 * all. After connect the three are the same object: the same
 * `lk.transcription` streams, the same `lk.agent.state` attribute, the same
 * transcript on screen.
 *
 * Deliberately not here: no components package, no audio element in JSX, no
 * global store. The Room is a ref because it is not React state — what React
 * renders is what the room told us.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ParticipantKind,
  Room,
  RoomEvent,
  Track,
  type Participant,
  type TextStreamReader,
} from "livekit-client";

import { mintToken, observe, type Channel } from "./api";
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

const TRANSCRIPTION_TOPIC = "lk.transcription";
const CHAT_TOPIC = "lk.chat";

/** Which door this session came in by. `observe` is the only one that publishes nothing. */
export type Mode = Channel | "observe";

/** Where the session is. `ended` is a call that finished; `failed` is one that never opened. */
export type Phase = "idle" | "connecting" | "live" | "ended" | "failed";

/** Everything a screen needs to render one conversation, and the four verbs that drive it. */
export interface Live {
  mode: Mode | null;
  phase: Phase;
  error: string | null;
  room: string | null;
  lines: Line[];
  state: AgentState | null;
  audible: boolean;
  open: (mode: Mode, room?: string) => Promise<void>;
  close: () => Promise<void>;
  say: (text: string) => Promise<void>;
  listen: (on: boolean) => void;
}

/** Open, hold and close one session against this tenant's project. */
export function useRoom(tenant: string, project: string): Live {
  const room = useRef<Room | null>(null);
  const speakers = useRef<HTMLMediaElement[]>([]);
  const audibleRef = useRef(true);
  const typed = useRef(0);

  const [mode, setMode] = useState<Mode | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState<string | null>(null);
  const [lines, setLines] = useState<Line[]>([]);
  const [state, setState] = useState<AgentState | null>(null);
  const [audible, setAudible] = useState(true);

  const close = useCallback(async () => {
    const open = room.current;
    room.current = null;
    speakers.current.forEach((element) => element.remove());
    speakers.current = [];
    if (open) await open.disconnect();
    setPhase((was) => (was === "idle" || was === "failed" ? was : "ended"));
    setState(null);
  }, []);

  const open = useCallback(
    async (next: Mode, target?: string) => {
      await close();
      setMode(next);
      setPhase("connecting");
      setError(null);
      setLines([]);
      setName(target ?? null);
      const listen = next !== "observe";
      audibleRef.current = listen;
      setAudible(listen);
      try {
        const ticket =
          next === "observe"
            ? await observe(target ?? "")
            : await mintToken({ tenant, project, channel: next });
        const joined = new Room({ adaptiveStream: false, dynacast: false });
        wire(joined, { setLines, setState, speakers, audibleRef });
        room.current = joined;
        await joined.connect(ticket.url, ticket.token);
        if (next === "voice") await joined.localParticipant.setMicrophoneEnabled(true);
        if (listen) await joined.startAudio();
        setName(ticket.room);
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

  const listen = useCallback((on: boolean) => {
    audibleRef.current = on;
    speakers.current.forEach((element) => {
      element.muted = !on;
    });
    setAudible(on);
  }, []);

  useEffect(() => () => void close(), [close]);

  return { mode, phase, error, room: name, lines, state, audible, open, close, say, listen };
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

function isAgent(participant: Participant): boolean {
  return participant.kind === ParticipantKind.AGENT;
}

function stateOf(participant: Participant): AgentState | null {
  return isAgent(participant) ? agentState(participant.attributes[AGENT_STATE]) : null;
}

// stage-pinecall — the pinecall.io commercial deck, RE-IMAGINED AS VOICE.
//
// The original (`~/pinecall/presentations/decks/pinecall.html`) is a slide deck
// you READ, with a live demo bolted on. This is the inversion: the deck is
// SPOKEN, the UI reveals itself at the pace of the voice, and the same session
// that narrates is the one the visitor interrupts to ask.
//
// Two slides, on purpose: the cover (which is also the START) and "las
// plataformas están dadas vuelta" — the argument the whole deck rests on.
//
// Run: PORT=4620 node server.mjs   →  http://127.0.0.1:4620
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, resolve } from "node:path";
import { Pinecall } from "@pinecall/sdk";

const PORT = Number(process.env.PORT || 4620);
const API_KEY = process.env.PINECALL_API_KEY;
const VOICE = process.env.PINECALL_API_URL || "https://voice.pinecall.io";
const SLUG = process.env.STAGE_SLUG || "dev-berna-stage-pinecall";
if (!API_KEY) throw new Error("PINECALL_API_KEY is required");

/** The deck: what the page SAYS, and what the presenter knows behind it. */
export const SLIDES = [
  {
    id: "cover",
    title: "Agentes de voz que viven dentro de tu producto",
    say:
      "Bienvenido. Esta presentación no se lee: se escucha. Soy el mismo agente " +
      "que Pinecall pone dentro de tu producto, y ahora mismo estoy narrando mi " +
      "propio deck. Cuando quieras, me interrumpís y preguntás.",
    notes:
      "La plataforma code-first para agentes de voz, chat y WhatsApp. Un SDK, cinco " +
      "canales: Phone, WhatsApp, WebRTC, Chat y SIP. Latencia sub-segundo, más de 60 " +
      "idiomas. SDK v0.3.2. El botón de start existe por dos razones: es UX, y es " +
      "técnicamente obligatorio — un navegador no deja hablar a una página sin un gesto.",
  },
  {
    id: "inverted",
    title: "Las plataformas de voz están dadas vuelta",
    say:
      "Las plataformas tradicionales te piden que configures el agente en su " +
      "dashboard, que definas tus tools como esquemas JSON, y que expongas webhooks " +
      "públicos. Tu aplicación termina adaptándose a la plataforma.",
    say2:
      "Pinecall lo da vuelta. El agente es tu código. Las tools son funciones " +
      "locales, las que ya escribiste. No agregás ni una superficie pública nueva. " +
      "La plataforma se adapta a tu aplicación.",
    notes:
      "Es el argumento sobre el que descansa todo el deck. Consecuencias concretas: " +
      "no hay un segundo lugar donde vive la lógica, las tools corren con tu base de " +
      "datos y tus permisos, y no hay endpoint nuevo que auditar ni asegurar.",
  },
  {
    id: "split",
    title: "División del trabajo: vos el qué, Pinecall el cómo",
    say:
      "Entonces, ¿quién hace qué? La división es simple: vos tenés el qué, " +
      "y Pinecall corre el cómo.",
    notes:
      "Tu código es dueño de: los prompts y la personalidad del agente; las tools, " +
      "con acceso directo a tu base de datos; la lógica de negocio y las validaciones; " +
      "y el historial de la conversación. El servidor de voz corre: el transporte de " +
      "audio por WebRTC, Twilio y SIP; el speech-to-text y el text-to-speech con los " +
      "mejores proveedores; la detección de voz y los turnos; y la mezcla, el barge-in " +
      "y el streaming en vivo. Vos no reimplementás nada de la pila de voz; nosotros " +
      "no tocamos tu lógica.",
  },
  {
    id: "channels",
    title: "Un agente. Todos los canales.",
    say:
      "El mismo prompt, las mismas tools, el mismo código, en cada canal. " +
      "Agregar el próximo canal es una línea.",
    notes:
      "Cinco canales sobre el mismo agente. Voz: Teléfono (Twilio gestionado o tu " +
      "propio carrier, números en más de 100 países), WebRTC (widget en el navegador, " +
      "peer-to-peer, sub-segundo) y SIP (trunks empresariales, integra con centrales " +
      "existentes). Texto: WhatsApp (Meta Cloud API, transcribe notas de voz solo) y " +
      "Chat web (widget o headless, escala a llamada sin perder el hilo). El punto: no " +
      "hay un agente por canal — es uno solo, y el canal es config, no reescritura.",
  },
];

const DECK_XML = SLIDES.map(
  (s, i) =>
    `  <slide n="${i + 1}" title="${s.title}">\n    <spoken>${s.say}${
      s.say2 ? " " + s.say2 : ""
    }</spoken>\n    <notes>${s.notes}</notes>\n  </slide>`,
).join("\n");

const PROMPT = `Sos el agente que está DETRÁS de una presentación en vivo de la
plataforma Pinecall. Hablás español, en tono profesional y cercano, de igual a
igual con alguien técnico.

LA PÁGINA HABLA, NO VOS. Cada párrafo del deck lo dice la página con el comando
\`say\` y entra en tu historial como un turno tuyo. Nunca repitas una slide salvo
que te lo pidan: estás acá para lo que pasa DESPUÉS, cuando el visitante
pregunta.

EL DECK, que es lo único que sabés con certeza:
<presentation slides="${SLIDES.length}">
${DECK_XML}
</presentation>

Los <notes> son del autor: la verdad técnica que la slide no muestra. Usalos
cuando la pregunta pasa por encima de lo que se dijo en voz alta.

Respondé corto: dos o tres frases, es una conversación sobre una slide, no una
clase. Si algo queda fuera del deck, decilo derecho.`;

const pc = new Pinecall({ apiKey: API_KEY, apiUrl: VOICE });
const agent = pc.agent(SLUG, {
  prompt: PROMPT,
  llm: process.env.STAGE_LLM || "openai/gpt-5.4-nano",
  voice: "elevenlabs/matilda",
  // DECLARED, never inherited: unset, the STT client defaults to flux while the
  // turn detection is derived for plain deepgram, and the visitor's speech
  // arrives as ".". `flux-multi` is the Spanish-capable one.
  stt: "deepgram/flux-multi",
  language: "es",
  // NO GREETING. A stage session opens silent: the PAGE speaks first, and an
  // agent that greets talks over the first paragraph.
  allowedOrigins: ["http://127.0.0.1:*", "http://localhost:*"],
});
agent.on("call.started", () => console.log("[deck] alguien abrió la presentación"));
agent.on("user.message", (e) => console.log(`[deck] visitante: ${e.text ?? ""}`));

async function mintToken() {
  const url = new URL("/webrtc/token", VOICE);
  url.searchParams.set("agent_id", SLUG);
  url.searchParams.set("say", "9000"); // characters this deck may speak
  const res = await fetch(url, { headers: { Authorization: `Bearer ${API_KEY}` } });
  if (!res.ok) throw new Error(`mint ${res.status}: ${await res.text()}`);
  return res.json();
}

const TYPES = { ".html": "text/html", ".mjs": "text/javascript", ".css": "text/css" };
// ONE stage.mjs, in one place. Copying it here would be the second truth that
// goes stale the first day.
const SHARED = { "/stage.mjs": resolve(import.meta.dirname, "../stage-demo/stage.mjs") };

createServer(async (req, res) => {
  const path = new URL(req.url, "http://x").pathname;
  try {
    if (path === "/token") {
      const t = await mintToken();
      res.writeHead(200, { "content-type": "application/json", "cache-control": "no-store" });
      return res.end(JSON.stringify({ ...t, server: VOICE }));
    }
    if (path === "/deck.json") {
      res.writeHead(200, { "content-type": "application/json" });
      return res.end(JSON.stringify(SLIDES));
    }
    const file = SHARED[path] ?? join(import.meta.dirname, path === "/" ? "index.html" : path.slice(1));
    const body = await readFile(file);
    res.writeHead(200, {
      "content-type": TYPES[extname(file)] ?? "application/octet-stream",
      "cache-control": "no-store",
    });
    res.end(body);
  } catch (e) {
    res.writeHead(path === "/token" ? 502 : 404, { "content-type": "text/plain" });
    res.end(String(e?.message ?? e));
  }
}).listen(PORT, "127.0.0.1", () =>
  console.log(`[deck] http://127.0.0.1:${PORT} — agente ${SLUG}`),
);

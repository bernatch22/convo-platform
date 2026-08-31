/* The voices this account actually owns, so a supervisor picks a name and not a hex string.
 *
 * ElevenLabs has no "list my voices" call on the control plane yet, so these
 * three are the ones CLAUDE.md pins for the project — the same ids the tenants
 * ship with. The select always keeps a free-text escape hatch: the platform
 * accepts ANY voice id, and this list is a convenience, never a whitelist.
 */

/** One ElevenLabs voice the account is known to have, with the name a human recognises. */
export interface KnownVoice {
  id: string;
  name: string;
  note: string;
}

export const KNOWN_VOICES: KnownVoice[] = [
  {
    id: "UOIqAnmS11Reiei1Ytkc",
    name: "Carolina",
    note: "Spanish woman · es_ES · peninsular, conversational — the platform default",
  },
  { id: "h2cd3gvcqTp3m65Dysk7", name: "Carolina Ruiz", note: "es_ES · alternative" },
  { id: "gD1IexrzCvsXPHUuT0s3", name: "Sara Martin 3", note: "es_ES · alternative" },
];

/** The account name for a voice id, or null when it is one this console does not know. */
export function voiceName(id: string): string | null {
  return KNOWN_VOICES.find((voice) => voice.id === id)?.name ?? null;
}

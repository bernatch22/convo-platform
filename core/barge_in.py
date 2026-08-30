"""Barge-in: deciding whether a user turn that landed on the agent's voice is a murmur.

A caller who says "vale" while the agent is mid-sentence is agreeing, not
taking the floor. LiveKit's own filter is `InterruptionOptions.min_words`,
which is a word COUNT and runs before the interruption is made — it catches
"vale" and "mm" and lets "vale vale" and "sí sí" straight through. This module
is the second net: it knows WHICH words a Spanish speaker murmurs.

Where each net sits in 1.7.1, verified in `voice/agent_activity.py`:

  `_user_turn_committed` (line ~2461)   `min_words` — BEFORE the interruption.
                                        The turn is discarded whole: no reply,
                                        and the agent never stops talking.
  `_cancel_speech_pause` (line ~2566)   the paused speech is interrupted here.
  `on_user_turn_completed` (line ~2588) our stoplist — StopResponse cancels the
                                        REPLY, and nothing else.

So a multi-word murmur still cuts the agent's audio; what this saves is the
answer to it, which on a phone call is the part the caller actually hears as a
mistake. Upstream has no hook to un-interrupt a speech that was already cut:
the only resume path is `resume_false_interruption`, and `_user_turn_committed`
cancels its timer for any turn that is going to reply. Documented on the card.

Open source note: the list is data. A project sets `Project.backchannels` and
core never learns another language.
"""

import unicodedata

# What a Spanish speaker says to mean "I am still here, keep going". Kept short
# on purpose: every word added here is a word the caller can no longer say on
# its own, and "vale" alone IS a valid yes when the agent is not speaking.
SPANISH_BACKCHANNELS = frozenset(
    {
        "aja",
        "ah",
        "ajam",
        "ya",
        "claro",
        "vale",
        "si",
        "ok",
        "okay",
        "mm",
        "mmm",
        "hm",
        "hmm",
        "eh",
        "bien",
        "exacto",
        "perfecto",
        "entiendo",
        "de",
        "acuerdo",
    }
)

_STRIP = "¿?¡!.,;:…\"'()-— "


def is_backchannel(text: str, words: frozenset[str] = SPANISH_BACKCHANNELS) -> bool:
    """True when every word of the turn is a murmur — an empty turn is not one."""
    tokens = [_fold(token) for token in text.split()]
    tokens = [token for token in tokens if token]
    return bool(tokens) and all(token in words for token in tokens)


def holds_the_floor(session) -> bool:
    """True when the agent was speaking, or was speaking until this very turn cut it.

    `current_speech` is the handle the activity is playing out. It survives the
    interruption that `_cancel_speech_pause` makes just before
    `on_user_turn_completed` — the scheduling task nils it later — so a turn
    that barged in still sees it, and a turn that arrived into silence sees
    None. That ordering is a race we lose on a fast machine, which is exactly
    why `min_words=2` stays the primary filter and this one is the second.
    """
    if getattr(session, "agent_state", None) == "speaking":
        return True
    return getattr(session, "current_speech", None) is not None


def backchannels_of(project) -> frozenset[str]:
    """The project's own stoplist, folded like the transcript, else the Spanish default."""
    words = getattr(project, "backchannels", None)
    return frozenset(_fold(word) for word in words) if words else SPANISH_BACKCHANNELS


def _fold(token: str) -> str:
    """lowercase, punctuation off, accents off: `¡Ajá!` and `aja` are one word."""
    stripped = token.strip(_STRIP).lower()
    decomposed = unicodedata.normalize("NFD", stripped)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")

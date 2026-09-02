"""Barge-in: deciding whether a user turn that landed on the agent's voice is a murmur.

Decisions: docs/decisions/convo.session.barge_in.md
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
    """True when the agent was speaking, or was speaking until this very turn cut it."""
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

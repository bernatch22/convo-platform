"""The four sentences a caller hears when a tool call cannot produce a result.

A failed tool call is still a turn of the conversation: the model reads the
message and says it, so it must sound like the project. Register is project
data, not platform data — a clinic that addresses patients as "usted" cannot
suddenly say "¿puedo ayudarte?" because a database timed out. Core therefore
ships a neutral default per failure and a project overrides any of them through
`Project.messages`.

Framework-agnostic on purpose: four keys, a dict of defaults and one lookup, so
the executor of any agent runtime can reuse them.
"""

from collections.abc import Mapping

UNKNOWN_TOOL = "unknown_tool"
NO_ADAPTER = "no_adapter"
TIMEOUT = "timeout"
FAILURE = "failure"

DEFAULTS: dict[str, str] = {
    UNKNOWN_TOOL: "No dispongo de esa función ahora mismo. ¿Puedo ayudarte de otra forma?",
    NO_ADAPTER: "No puedo acceder a ese sistema ahora mismo. ¿Puedo ayudarte de otra forma?",
    TIMEOUT: "El sistema está tardando demasiado en responder. ¿Lo intento de nuevo?",
    FAILURE: "No he podido completar esa consulta. ¿Quieres que lo intente de nuevo?",
}


def sentence(messages: Mapping[str, str], key: str) -> str:
    """The project's sentence for this failure, falling back to the platform default."""
    return messages.get(key) or DEFAULTS[key]

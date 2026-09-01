"""Handing the call to a person as a VERB of the agent: the number, the rule, the words.

`core.security.control` already lets a supervisor move a call from the desk.
This is the other half the spec asks for: the agent itself deciding «le paso
con un compañero» because the caller asked for one, or because what they need
is not something reception can do.

Three things live here and nothing else, so that the console, the executor and
the prompt all read one declaration:

- **the number is project data.** `Project.transfer_number` is where a call
  goes, in E.164, and it is overridable from the console like the voice and the
  greeting — a business changes the phone its reception overflows to far more
  often than it redeploys.
- **a tool that cannot work is not offered.** No number means the model never
  sees `transfer_to_human` in its tool list, and the console greys the verb out
  with the sentence a PUT would be refused with. That is the same
  `unavailable_reasons` idiom `core.pipeline` uses for a provider whose key
  this box does not carry, and it is the opposite of a runtime surprise: a
  transfer that fails in the middle of a call costs a caller their patience,
  and one that was never possible costs them nothing.
- **the words.** The paragraph that teaches a stage to announce the handover
  before it happens, and the three sentences the tool answers with.

Framework-free on purpose: it imports `core.telephony.transfer` for the E.164
rule and nothing else, so `core.pipeline` — which every console read goes
through — does not drag the agent runtime in behind it. The half that touches
livekit is `core.adapters.human` (the run) and `core.agents.human` (the door
the model knocks on).
"""

from core.context import Project
from core.telephony.transfer import WARM, TransferRefused, phone_number
from core.tools.contract import SideEffect, ToolSpec

# The project field the console may set, and the name the model calls.
FIELD = "transfer_number"
TOOL = "transfer_to_human"

# 25 s of ringing (`transfer.RINGING_S`) plus the REFER round trip: a timeout
# under the ring would abandon a colleague who was about to pick up.
TIMEOUT_S = 30.0


def summarise(payload: dict) -> str:
    """The one line a transfer leaves in the log: the mode, how it ended, where it went."""
    return f"{payload.get('mode')} → {payload.get('outcome')} ({payload.get('to')})"


TRANSFER_TO_HUMAN = ToolSpec(
    name=TOOL,
    side_effect=SideEffect.WRITE,
    timeout_s=TIMEOUT_S,
    result_summary=summarise,
)

# --- what the console is told ------------------------------------------------

NOT_DECLARED = (
    f"this project does not declare {TOOL!r} in its tool catalog, so no number will make the "
    "agent offer it. That is a deploy decision, not a console one: add the spec to the "
    "project's catalog (core.telephony.human.TRANSFER_TO_HUMAN) and redeploy."
)

NO_NUMBER = (
    f"{FIELD} is empty, so this project has no human to hand a call to and the model is never "
    f"offered {TOOL!r} at all. A tool that cannot work is not offered: a transfer that fails "
    "mid-call costs a caller their patience, one that was never possible costs them nothing. "
    "Set an E.164 number below (+34910000000) and the NEXT session carries the verb."
)

OFFERED = (
    "the agent may hand a call to this number on its own, after announcing it. A PSTN call "
    "is moved with a REFER on its own leg; a browser voice call gets this number dialled "
    "INTO its room instead — a warm bridge, which needs SIP_OUTBOUND_TRUNK_ID on the box and "
    "is refused at the door without it; a chat gets an honest refusal, there being no audio "
    "to join. Every attempt is one `supervisor.transfer` line in the caller's log with its "
    "mode and its outcome."
)


def refusal(value: str) -> str | None:
    """Why this number is refused, or None when a call could really be handed to it.

    Empty is not a refusal: it is how the console CLEARS the number, and
    clearing it takes the verb away from the model rather than leaving it a tool
    that fails. Everything else has to be a number `TransferSIPParticipant` can
    dial — E.164, `+` and digits — because a REFER carries a `tel:` URI and a
    name, an extension or a spaced-out number reaches no carrier at all.
    """
    if not value:
        return None
    try:
        phone_number(value)
    except TransferRefused as refused:
        return (
            f"{value!r} is not a number a call can be handed to: {refused}. The console stores "
            "E.164 — a leading '+', a country code and digits, no spaces — because the transfer "
            "is a SIP REFER carrying a tel: URI. Leave it empty to take the verb away instead."
        )
    return None


def number_of(project: Project) -> str:
    """Where this project's transfers go, stripped; "" when it names nobody."""
    return (project.transfer_number or "").strip()


def declared(project: Project) -> bool:
    """Whether the project opted into the verb at all — the catalog is the opt-in."""
    return project.tools.get(TOOL) is not None


def offered(project: Project) -> bool:
    """Whether this project's next session shows the model a transfer tool."""
    return declared(project) and bool(number_of(project))


def unavailable(project: Project) -> str | None:
    """Why the model is not offered the verb, or None when it is."""
    if not declared(project):
        return NOT_DECLARED
    if not number_of(project):
        return NO_NUMBER
    return None


def view(project: Project) -> dict:
    """The transfer half of the console's phone block: the number, and why it is or is not live.

    `unavailable_reasons` is keyed by the TOOL name and carries the sentence
    verbatim, exactly like `stt_view` and `llm_view`: the console greys the verb
    and repeats the server's own words instead of keeping a second copy of the
    rule.
    """
    why = unavailable(project)
    return {
        "tool": TOOL,
        "number": number_of(project),
        "declared": declared(project),
        "offered": offered(project),
        "unavailable_reasons": {TOOL: why} if why else {},
        "note": why or OFFERED,
    }


# --- what the model is told --------------------------------------------------

# The prompt half of the verb, and it is deliberately SMALL. Anthropic's current
# guidance is to remove over-prompting — "instructions like 'If in doubt, use
# [tool]' will cause overtriggering", and aggressive "you MUST use this tool
# when…" language should be dialled back to plain "use this tool when…" — and a
# tool's own description is already loaded into the system prompt, so a
# paragraph that repeats the docstring's trigger rules is pure noise on every
# stage, including the stages that will never transfer anybody. So the trigger
# ("úsala cuando…") and the outcome handling live in the DOCSTRING
# (`core.agents.human.transfer_to_human`), where the model reads them at the
# moment it is deciding, and what stays here is the one thing a tool
# description cannot express: the announcement is a spoken TURN, and it has to
# happen before the line moves. Positive, with its motivation attached, because
# "tell Claude what to do instead of what not to do".
#
# The first version was nine sentences of prohibitions in the LAST slot of every
# stage prompt. It was suspected of a flake and it was innocent — see `protocol`
# for the 154 runs. This version is a third the size and follows the guidance;
# it did not move the flake either, because the flake was never about the words.
PROTOCOL = """\
<derivacion>
Cuando vayas a pasar la llamada a un compañero, anúncialo primero en una frase corta y con
el mismo trato que lleves usando en la llamada —«le paso con un compañero, un momento»— y
deja que esa frase sea tu turno entero. Quien llama necesita oír que va a esperar antes de
que la línea se mueva: un traspaso hecho en silencio se oye como una llamada que se corta.
</derivacion>
"""

# What the tool answers with. One sentence per thing that can happen, and each
# one written as an instruction to the model rather than as a line to read out:
# what the caller hears is the model's, in the project's own register.
MOVED = (
    "La llamada está pasando a un compañero: quien llamaba deja de estar contigo. No digas "
    "nada más y no te despidas otra vez."
)

# The warm half of MOVED: on a browser call nobody leaves — the colleague ARRIVES.
JOINED = (
    "El compañero está entrando a la llamada y quien llama ya puede hablar con él. No digas "
    "nada más y no te despidas: la conversación sigue entre ellos."
)

FAILED = (
    "El traspaso no ha podido hacerse ({outcome}) y quien llama SIGUE contigo en la línea, "
    "esperando. Díselo con naturalidad y sin tecnicismos —no has podido pasarle con un "
    "compañero—, ofrécele el teléfono del centro que tienes en tu información por si prefiere "
    "llamar, y sigue ayudándole tú con lo que necesitaba."
)

NO_PHONE_CALL = (
    "Esta conversación no es una llamada de teléfono, así que no hay ninguna línea que pasar a "
    "un compañero y no se ha hecho nada. Díselo tal cual, ofrécele el teléfono del centro que "
    "tienes en tu información para que le atienda una persona, y sigue ayudándole tú mientras "
    "tanto."
)

# A voice call the platform cannot bridge right now — refused at the door, nothing rang.
NO_BRIDGE = (
    "Ahora mismo no es posible pasar esta llamada a un compañero y no se ha hecho nada: quien "
    "llama sigue contigo. Díselo con naturalidad, ofrécele el teléfono del centro que tienes en "
    "tu información para que le atienda una persona, y sigue ayudándole tú mientras tanto."
)

# The situation-paragraph for a business with nobody on the other end. It names
# the situation and never the tool: a rule about a verb the model does not have
# is the surest way to have it reach for one.
ALONE = """\
<derivacion>
En esta línea no hay nadie más a quien pasar la llamada: quien atiende eres tú y no tienes
forma de transferir a nadie. Si te piden hablar con una persona, se lo dices con naturalidad
y sin disculparte de más —quien está al teléfono eres tú y les atiendes igual—, les ofreces
resolverlo tú o los otros canales del negocio que tengas en tu información, y sigues con lo
que necesitaban. Lo que no haces nunca es prometer un traspaso: decir «ahora mismo te paso»
y no pasar a nadie deja a quien llama esperando una voz que no va a llegar.
</derivacion>
"""


def protocol(project: Project) -> str:
    """The paragraph a stage's prompt closes with about handing the call to a person.

    Three answers, and the third is the one that was measured. A project that
    declares the spec and names a number is taught the verb; one that declares
    it and names nobody is taught that there IS nobody, which is a fact about
    the deployment and not a rule about a tool it does not have; and a project
    that never declared it is told nothing at all, because core does not invent
    policy for a business that has not asked the question.

    The middle case exists because of one shop golden on 2026-08-31. Asked
    «pásame con una persona», tienda-sur — no number, no tool, no paragraph —
    answered «Entiendo, ahora mismo te paso», which is a promise nothing in the
    platform can keep: the caller waits for a voice that never arrives. Silence
    is not honesty. Naming the TOOL there would be the other mistake — a rule
    about a verb the model does not have is the surest way to have it reach for
    one — so the paragraph names the situation instead.

    Spanish, like `core.security.protocol.SUPERVISOR_PROTOCOL` and for the same
    reason: both demo tenants are. A project in another language writes its own
    paragraph and appends that instead.

    **What this paragraph costs, measured (2026-09-01, 154 runs of
    `test_a_caller_with_no_cita_is_handed_over_to_the_stage_that_creates_one`,
    claude-haiku-4-5).** The test went flaky when this card landed and the
    paragraph was the prime suspect — its wording, and its position in the last,
    most-recent slot of the prompt. Both were innocent:

    | cell                                          | pass/valid | fail |
    |-----------------------------------------------|-----------:|-----:|
    | card reverted — no tool, no paragraph          |      38/40 |   5% |
    | v1: nine sentences of prohibitions, last slot  |      15/20 |  25% |
    | v2: tool named in the clause, moved off last   |      31/40 |  22% |
    | **no paragraph at all, tool still offered**    |      16/20 |  20% |
    | v3: this one — short, positive, docstring-led  |      28/34 |  18% |

    Every cell with the TOOL is 18-25% and they are indistinguishable from each
    other (v1 vs v2 p=1.0, v1 vs v3 p=0.73, paragraph vs no paragraph p=1.0).
    Pooled, tool-present is 90/114 against the floor's 38/40 — **p=0.025**. The
    cost is the TOOL on the stage's surface, not any sentence in the prompt:
    `Identify` now chooses among one more verb, and it is the published effect
    that every tool an agent carries is one more distraction it must ignore.

    That is a real price for a real feature and it is written down rather than
    softened. The verb has to be reachable in the first ten seconds of a call —
    that is when somebody asks for a person — so taking it off the entry stage
    would cost more than it saves. If it has to be bought back, the lead is
    `Identify`'s own instructions, not this paragraph.
    """
    if not declared(project):
        return ""
    return PROTOCOL if offered(project) else ALONE


def said(payload: dict) -> str:
    """What the model reads back after a transfer attempt — an outcome, never a stack trace.

    The mode decides the success sentence, because the two ends differently:
    a cold REFER takes the caller AWAY, a warm bridge brings the colleague IN.
    """
    if payload.get("ok"):
        return JOINED if payload.get("mode") == WARM else MOVED
    return FAILED.format(outcome=payload.get("outcome", "sin respuesta"))

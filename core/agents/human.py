"""The door the model knocks on to hand its call to a person, and the rule that hides it.

One `@function_tool`, module-level rather than a method of `TenantAgent`, for
the only reason that matters here: a method is on every stage of every project
forever, and this verb has to be able to be ABSENT. A project that names no
`transfer_number` never sees it in its tool list — not greyed out, not failing
politely, absent — which is the same promise `core.pipeline` makes about a
provider whose key this box does not carry.

It is a thin door on purpose. The decision of what a transfer costs and where
it goes is `core.telephony.human`; the run is `core.adapters.human`, reached
through the executor like every other write, so the guard, the timeout and the
project's own failure sentence all apply. What is left here is the docstring —
which is the schema Claude reads before it decides — and the waiting.

**The waiting is the load-bearing line.** A model that announces «le paso con
un compañero, un momento» and calls the tool in the same turn has queued that
sentence for TTS, not spoken it. REFER the leg first and the carrier takes the
call mid-word: the caller is handed to a colleague having heard nothing, which
is exactly the abandonment the announcement exists to prevent.
`ctx.wait_for_playout()` is the framework's answer, and it costs nothing on a
channel with no audio.
"""

from livekit.agents import RunContext, function_tool

from core.context import TenantContext
from core.telephony import human


@function_tool
async def transfer_to_human(ctx: RunContext[TenantContext]) -> str:
    """Pasa esta llamada a una persona del centro, que sigue la conversación en tu lugar.

    Llámala cuando quien llama pida hablar con una persona, o cuando lo que necesita no
    sea algo que puedas resolver tú desde aquí. Antes de llamarla anúnciaselo en una frase
    corta —«le paso con un compañero, un momento»— y que esa frase sea tu turno entero: no
    te despidas ni des el traspaso por hecho, porque hasta que esta herramienta no responda
    no ha ocurrido nada.

    Devuelve lo que ha pasado de verdad: que la llamada está pasando a un compañero, o que
    no ha podido pasarse y quien llama sigue contigo en la línea. Cuenta eso y solo eso; si
    no ha podido hacerse, sigue tú atendiéndole.
    """
    tc = ctx.userdata
    # The announcement is queued, not spoken, when the model calls a tool in the
    # same turn: REFER first and the carrier takes the call mid-word.
    await ctx.wait_for_playout()
    return human.said(await tc.tools.call(human.TOOL, {}))


def transfer_tools(tc: TenantContext) -> list:
    """The transfer verb when this project can really run one, and nothing at all when it cannot.

    The whole of the `unavailable_reasons` idiom on the agent's side: one read
    of the project, at the moment the stage is built, and the model's tool list
    either has the verb or has never heard of it.
    """
    return [transfer_to_human] if human.offered(tc.project) else []

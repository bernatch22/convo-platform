"""The door the model knocks on to hand its call to a person, and the rule that hides it.

Decisions: docs/decisions/convo.agents.human.md
"""

from livekit.agents import RunContext, function_tool

from convo.domain.context import TenantContext
from convo.telephony import human


@function_tool
async def transfer_to_human(ctx: RunContext[TenantContext]) -> str:
    """Pasa esta llamada a una persona del centro, que sigue la conversación en tu lugar.

    Úsala cuando quien llama pida hablar con una persona, o cuando lo que necesita no sea
    algo que puedas resolver con tus otras herramientas.

    Antes de llamarla, anuncia el traspaso en una frase corta —«le paso con un compañero,
    un momento»— y que esa frase sea tu turno entero.

    Devuelve lo que ha pasado de verdad. Si la llamada está pasando a un compañero, quien
    llamaba deja de estar contigo. Si no ha podido hacerse, sigue en la línea contigo y
    esperando: cuéntaselo con naturalidad, ofrécele lo que sí puedas hacer y sigue
    atendiéndole tú.
    """
    tc = ctx.userdata
    # The announcement is queued, not spoken, when the model calls a tool in the
    # same turn: REFER first and the carrier takes the call mid-word.
    await ctx.wait_for_playout()
    return human.said(await tc.tools.call(human.TOOL, {}))


def transfer_tools(tc: TenantContext) -> list:
    """The transfer verb when this project can really run one, and nothing at all when it cannot."""
    return [transfer_to_human] if human.offered(tc.project) else []

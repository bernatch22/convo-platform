"""Reception: open the call, find the customer's booking, hand the call to Desk."""

from convo.agents import RunContext, TenantAgent, function_tool
from convo.domain.context import TenantContext
from convo.prompting import stage_prompt

from .. import tools


class Reception(TenantAgent):
    """Greets, asks for the booking reference, and looks it up."""

    def __init__(self, tc: TenantContext) -> None:
        super().__init__(tc, instructions=stage_prompt(tc, "reception"))

    def summary(self) -> str:
        """What Desk needs: WHICH booking this is, and deliberately not what state it is in.

        Identity travels, state does not. A status read a minute ago is a
        status that may have changed; the next stage asks the system instead of
        inheriting a sentence. TODO(copy): keep this line to identity only.
        """
        booking = self.tc.customer
        if not booking:
            return "Todavía no se ha localizado ninguna reserva."
        return (
            f"Reserva localizada: {booking['reference']}, a nombre de {booking['name']}. Es la "
            "reserva de la que va esta llamada. Su estado no está en esta nota a propósito: se "
            "consulta en el sistema antes de contarlo."
        )

    @function_tool
    async def identify_booking(self, ctx: RunContext[TenantContext], reference: str) -> str | tuple:
        """Busca la reserva del cliente en el sistema y da paso a resolverla.

        Llámala en cuanto tengas la referencia. Es lo primero que hay que hacer en la
        llamada: hasta que la reserva no está localizada no puedes hablar de su estado, ni
        de su fecha, ni de cancelarla. No la llames dos veces con el mismo dato; si no ha
        encontrado nada, pide que te lo repita y vuelve a llamarla con lo que te diga.

        Args:
            reference: la referencia tal y como la haya dicho el cliente, empiece por EX o
                no ("EX-1001", "ex 1001", "1001"). No la corrijas ni la completes tú.

        Devuelve la reserva con su servicio, su fecha y su estado, o la indicación de que no
        consta ninguna con esa referencia.
        """
        tc = ctx.userdata
        booking = await tc.tools.call("find_booking", {"reference": reference})
        if not booking:
            return tools.NOT_FOUND
        tc.customer = booking
        from .desk import Desk

        return self.hand_off(Desk(tc))

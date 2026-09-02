"""Identify: open the call, find the customer's order, hand the call to OrderDesk."""

from convo.agents import RunContext, TenantAgent, function_tool
from convo.domain.context import TenantContext
from convo.prompting import stage_prompt

from .. import messages


class Identify(TenantAgent):
    """Greets, asks for the order number (or the mobile), and looks the order up."""

    def __init__(self, tc: TenantContext) -> None:
        super().__init__(tc, instructions=stage_prompt(tc, "identify"))

    def summary(self) -> str:
        """What OrderDesk needs: WHICH order this is, and deliberately not what state it is in.

        Identity travels, state does not. The status, the delivery date and the
        tracking code are the things that change and the things a cancellation
        turns on, so the next stage reads them from the order system instead of
        inheriting a sentence written a minute ago. Handed the whole row, the
        model answered "¿por dónde va?" out of the note without consulting
        anything — a right answer today and a stale one the first time a
        warehouse is quicker than a conversation.
        """
        order = self.tc.customer
        if not order:
            # The only way out of this stage without an order is the ticket desk, and an
            # incident needs no order at all. Answering "todavía no se ha localizado ningún
            # pedido" sent the next stage back to asking for one — a summary arrives as a
            # turn the model ANSWERS, so a note about a missing order becomes a question
            # about it (measured: «¿qué le ha pasado con su pedido?» in a call that had
            # never mentioned one).
            return (
                "No hay ningún pedido localizado en esta llamada, y una incidencia no necesita "
                "ninguno."
            )
        return (
            f"Pedido localizado: {order['order_id']}, a nombre de {order['name']}. Es el pedido "
            "del que va esta llamada. Su estado, su fecha de entrega y su seguimiento no están "
            "en esta nota a propósito: cámbianlos en el almacén, así que se consultan en el "
            "sistema antes de contarlos."
        )

    @function_tool
    async def identify_order(
        self,
        ctx: RunContext[TenantContext],
        order_number: str | None = None,
        phone: str | None = None,
    ) -> str | tuple:
        """Busca el pedido del cliente en el sistema de la tienda y da paso a resolverlo.

        Llámala en cuanto tengas el número de pedido, o el móvil de la compra si el cliente
        no tiene el número a mano. Es lo primero que hay que hacer en la llamada: hasta que el
        pedido no está localizado no puedes hablar de su estado, ni de fechas, ni de
        cancelarlo. No la llames dos veces con los mismos datos; si no ha encontrado nada,
        pide que te los repita y vuelve a llamarla con lo que te diga.

        Args:
            order_number: el número de pedido tal y como lo haya dicho el cliente, empiece
                por TS o no ("TS-10432", "ts 10432", "10432"). No lo corrijas ni lo
                completes tú.
            phone: el móvil con el que se hizo la compra, solo los dígitos y solo si el
                cliente ya lo ha dicho ("600222333"). Omítelo mientras no lo sepas: con el
                número de pedido basta.

        Devuelve el pedido con su estado, su contenido, su importe y su seguimiento, o la
        indicación de que no consta ninguno con esos datos.
        """
        tc = ctx.userdata
        order = await tc.tools.call("find_order", {"order_id": order_number, "phone": phone})
        if not order:
            return messages.NOT_FOUND
        tc.customer = order
        from .order_desk import OrderDesk

        return self.hand_off(OrderDesk(tc))

    @function_tool
    async def start_ticket_desk(self, ctx: RunContext[TenantContext]) -> "TenantAgent":
        """Pasa la llamada al mostrador de incidencias, que es otra parte de la tienda.

        Llámala cuando el cliente hable de una incidencia y no de un pedido: quiere abrir una
        («quiero poner una reclamación», «el paquete llegó roto») o pregunta por una que ya
        tiene («¿cómo va mi incidencia?», «tengo el número TS-T algo»). En ese caso no le pidas
        el número de pedido: para una incidencia no hace falta.

        No la llames porque no encuentres el pedido. Un número mal oído se vuelve a pedir; una
        incidencia se abre porque el cliente tiene un problema, no porque el sistema no haya
        encontrado su compra.

        No necesita argumentos: allí le preguntan lo que haga falta.
        """
        tc = ctx.userdata
        from .ticket_desk import TicketDesk

        return self.hand_off(TicketDesk(tc))

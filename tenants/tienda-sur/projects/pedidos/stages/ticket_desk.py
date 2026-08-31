"""TicketDesk: write down what went wrong, and say how the customer's own incident stands.

A stage and not a branch, and the argument is ms-18's, run again on this shop.

That argument has two halves. The first is about consent: a stage with two
irreversible doors makes the (write, asking) pair the consent metric watches
ambiguous. It does not apply here — opening an incident is a WRITE, not an
irreversible, so `cancel_order` is still the only door in this project and the
graph is unchanged. The second half is the one that decides it: **does any
contract in the way say the order exists?** Identify's does, in five sentences
and in the shop's own information sheet ("hasta que el pedido no está
localizado no se habla de nada"), and OrderDesk's two tools take no arguments
at all *because* the order is already found. A customer ringing with a ticket
number and no order — the second call in "abre una y consúltala luego" — walks
into that wall, and widening Identify's rule to let them past would weaken the
rule that stops us cancelling somebody else's parcel.

So Identify grows a deliberate second exit, exactly as the clinic's did, and
this stage answers to a different contract: here what is known is the INCIDENT,
and the order is optional context. OrderDesk gets the same exit, because a
customer whose order is already on the table should not have to repeat it.

The prompt cost that a second stage usually carries was paid once and refunded
the same way ms-18 paid it: the shared `<shop_knowledge>` block is byte
identical across the four stages, so the cached prefix is the same object and
no existing golden moved.
"""

from core.agents import RunContext, TenantAgent, function_tool
from core.context import TenantContext

from .. import prompts, tools


class TicketDesk(TenantAgent):
    """Opens an incident with the customer's own words, and reads back the one they ask for."""

    def __init__(self, tc: TenantContext) -> None:
        super().__init__(tc, instructions=prompts.ticket_desk_prompt(tc))
        self.opened: dict[str, str] | None = None
        self.asking: str | None = None

    def summary(self) -> str:
        """What a later stage needs: the incident that now exists, in the words to read out.

        Two stages read it now. Farewell closes a call that filed one, and OrderDesk
        arrives when the customer went back to asking about the parcel — so the note
        has to be true for a desk that is NOT going to talk about the incident, which
        is why it never asks the next stage to bring it up.
        """
        if not self.opened:
            return "Todavía no se ha abierto ninguna incidencia."
        return (
            f"Incidencia {self.opened['ticket_id']} abierta y anotada. El cliente ya tiene el "
            f"número; un compañero la revisa y se le escribe.{self._asked()} Esta nota es para "
            "ti: no se lee en voz alta ni se resume al cliente."
        )

    def _asked(self) -> str:
        """The question that sent the call back, when one did — so it is not asked twice."""
        if not self.asking:
            return ""
        return (
            f" Lo que el cliente quiere ahora es esto y es a lo que respondes: «{self.asking}». "
            "Ya lo ha dicho, así que no se lo preguntes otra vez: míralo y contéstalo."
        )

    @function_tool
    async def open_ticket(
        self, ctx: RunContext[TenantContext], subject: str, phone: str | None = None
    ) -> str:
        """Abre una incidencia con el problema del cliente y te devuelve el número que darle.

        Llámala cuando el cliente cuenta algo que esta llamada no puede resolver sola —el
        paquete no ha llegado, ha llegado roto o cambiado, falta una prenda, el transportista
        no da señales, un cobro raro— y ya te ha dicho QUÉ le pasa. Si todavía no te lo ha
        contado, pregúntaselo antes: una incidencia sin asunto no la puede leer nadie.

        Args:
            subject: lo que le pasa, con las palabras del cliente y en una o dos frases. Escribe
                lo que ha dicho él, no lo que tú supongas: nada de números de pedido, de prendas
                ni de nombres que no haya dicho él en esta llamada.
            phone: el móvil al que podemos escribirle, solo si te lo acaba de decir y no
                habíamos localizado ya su pedido. Omítelo en cualquier otro caso.

        Devuelve el número de la incidencia —empieza por TS-T— y lo que se ha anotado en ella.
        """
        tc = ctx.userdata
        subject = tools.ticket_subject(subject)
        if not subject:
            return tools.NO_SUBJECT
        customer = tc.customer or {}
        ticket = await tc.tools.call(
            "open_ticket",
            {
                "subject": subject,
                # The shop already knows who you are when it found your order; when it did
                # not, the incident carries the number to call back on and the team asks the
                # rest. The model is never asked for a name it would have to remember.
                "name": customer.get("name", ""),
                "phone": phone or customer.get("phone", ""),
                "order_id": customer.get("order_id", ""),
            },
        )
        self.opened = ticket
        return tools.opened_line(ticket)

    @function_tool
    async def ticket_status(
        self, ctx: RunContext[TenantContext], ticket_id: str | None = None
    ) -> str:
        """Consulta cómo va una incidencia que ya está abierta, ahora mismo, en el sistema.

        Llámala siempre que el cliente pregunte por una incidencia suya, y llámala otra vez si
        vuelve a preguntar más adelante: entre una pregunta y otra un compañero puede haberla
        cogido. Nunca digas en qué estado está sin haberla consultado: tú no ves la cola, ella
        sí.

        Args:
            ticket_id: el número de la incidencia tal y como lo haya dicho el cliente, empiece
                por TS-T o no ("TS-T0001", "ts t 1", "1"). No lo corrijas ni lo
                completes tú. Omítelo si no lo tiene a mano y ya habíamos localizado su pedido:
                entonces se busca por el móvil de la compra.

        Devuelve la incidencia con su estado, cuándo se abrió, quién la lleva y lo que se anotó
        en ella, o la indicación de que no consta ninguna con esos datos.
        """
        tc = ctx.userdata
        ticket = await tc.tools.call(
            "ticket_status",
            {"ticket_id": ticket_id, "phone": (tc.customer or {}).get("phone")},
        )
        return tools.ticket_line(ticket) if ticket else tools.NO_TICKET

    @function_tool
    async def back_to_orders(self, ctx: RunContext[TenantContext], pregunta: str) -> "TenantAgent":
        """Devuelve la llamada al mostrador de pedidos, cuando el cliente vuelve a su pedido.

        En `pregunta` pones lo que acaba de preguntar, en sus palabras y en una frase
        —«cuándo llega mi pedido», «quiero cancelarlo»—, para que el mostrador le responda
        eso mismo y no se lo haga repetir.

        Llámala en cuanto el cliente vuelva a hablar de su pedido y no de la incidencia: dónde
        está, cuándo llega, si puede seguirlo o si quiere cancelarlo. Es el camino de vuelta
        del que vino, y existe porque una persona que entra a poner una incidencia sigue
        teniendo un pedido del que preguntar.

        No la llames si lo que pregunta es por su incidencia: eso lo resuelves tú aquí.

        """
        tc = ctx.userdata
        from .identify import Identify
        from .order_desk import OrderDesk

        # Symmetric to `start_ticket_desk`: what the customer just said travels with the
        # handoff, because a handoff copies no history in either direction.
        self.asking = pregunta.strip() or None

        # Back to the desk that knows the order — or to the front, when this call reached the
        # incidents without ever localising one: OrderDesk's whole contract is that the order
        # is already on the table, and arriving there without it would ask the customer for a
        # number in the middle of a conversation instead of at the start of it.
        return self.hand_off(OrderDesk(tc) if tc.customer else Identify(tc))

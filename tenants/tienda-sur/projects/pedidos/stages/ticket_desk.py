"""TicketDesk: write down what went wrong, and say how the customer's own incident stands.

Decisions: docs/decisions/tenants.tienda-sur.projects.pedidos.stages.ticket_desk.md
"""

from convo.agents import RunContext, TenantAgent, function_tool
from convo.domain.context import TenantContext
from convo.prompting import stage_prompt

from .. import helpers, messages


class TicketDesk(TenantAgent):
    """Opens an incident with the customer's own words, and reads back the one they ask for."""

    def __init__(self, tc: TenantContext) -> None:
        super().__init__(tc, instructions=stage_prompt(tc, "ticket_desk"))
        self.opened: dict[str, str] | None = None
        self.asking: str | None = None

    def summary(self) -> str:
        """What a later stage needs: the incident that now exists, in the words to read out."""
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
        subject = helpers.ticket_subject(subject)
        if not subject:
            return messages.NO_SUBJECT
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
        return helpers.opened_line(ticket)

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
        return helpers.ticket_line(ticket) if ticket else messages.NO_TICKET

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

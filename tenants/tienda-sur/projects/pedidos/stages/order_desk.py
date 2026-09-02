"""OrderDesk: say where the order is, and stop it while the warehouse still can.

Decisions: docs/decisions/tenants.tienda-sur.projects.pedidos.stages.order_desk.md
"""

from convo.agents import ConfirmTask, RunContext, TenantAgent, function_tool
from convo.domain.context import TenantContext
from convo.prompting import prompt, stage_prompt
from convo.tools.saga import Saga, SagaFailed

from .. import helpers, messages
from .farewell import Farewell

SMS_STEP = "send_sms"


class OrderDesk(TenantAgent):
    """Reads the order's real state back, and cancels it once the customer confirms."""

    def __init__(self, tc: TenantContext) -> None:
        super().__init__(tc, instructions=stage_prompt(tc, "order_desk"))
        self.cancelled: dict[str, str] | None = None
        self.problem: str | None = None

    def summary(self) -> str:
        """What the next stage needs: the cancellation if there is one, else the order."""
        if self.cancelled:
            return (
                f"Pedido {self.cancelled['order_id']} cancelado. El importe de "
                f"{self.cancelled['total']} vuelve por donde se pagó en tres a cinco días "
                "laborables y el SMS de confirmación ya se ha enviado."
            )
        order = self.tc.customer or {}
        if not order:
            return "Todavía no se ha localizado ningún pedido."
        said = (
            f" El cliente YA ha contado qué le pasa: «{self.problem}». No se lo preguntes otra "
            "vez —acaba de decirlo— y abre la incidencia con eso."
            if self.problem
            else ""
        )
        return (
            f"Pedido localizado: {order['order_id']}, a nombre de {order['name']}. Es el pedido "
            "del que va esta llamada, así que no vuelvas a pedir el número ni el móvil. Nada se "
            f"ha cancelado.{said} Esta nota es para ti: no se lee en voz alta ni se resume al "
            "cliente."
        )

    @function_tool
    async def order_status(self, ctx: RunContext[TenantContext]) -> str:
        """Consulta en el sistema en qué punto está el pedido del cliente, ahora mismo.

        Llámala siempre que el cliente pregunte por dónde va su pedido, cuándo le llega, si
        ya ha salido o si puede seguirlo, y llámala otra vez si vuelve a preguntarlo más
        adelante en la llamada: entre una pregunta y otra el pedido puede haber salido del
        almacén. Nunca digas un estado ni una fecha de entrega sin haberla llamado antes: tú
        no ves el almacén, ella sí.

        No necesita argumentos: el pedido ya está localizado desde el principio de la
        llamada.

        Devuelve el pedido con su estado, lo que lleva dentro, el importe, el envío con su
        fecha prevista y el número de seguimiento cuando ya lo tiene.
        """
        tc = ctx.userdata
        order = await self._reload(tc)
        return helpers.order_line(order) if order else messages.NOT_FOUND

    @function_tool
    async def request_cancellation(self, ctx: RunContext[TenantContext]) -> str | tuple:
        """Cancela el pedido del cliente, si el almacén todavía puede pararlo.

        Llámala en cuanto el cliente diga que quiere cancelar, sin preguntarle antes si se lo
        confirmas: la propia herramienta le lee el pedido y el importe y espera su sí. No
        necesita argumentos y cancela el pedido entero, que es lo único que se puede cancelar.

        Devuelve lo que ha pasado de verdad: que el pedido queda cancelado, que ya había
        salido y no se puede cancelar (con la devolución que hay que ofrecerle en su lugar),
        que el aviso por SMS no ha podido salir y por eso no se ha cancelado nada, o que el
        cliente no ha confirmado. Cuenta eso y solo eso.
        """
        tc = ctx.userdata
        order = await self._reload(tc)
        if not order:
            return messages.NOT_FOUND
        if not helpers.cancellable(order):
            return helpers.cannot_cancel(order)
        args = {"order_id": order["order_id"]}
        # The sentence the customer says yes to is rendered by us, from the row the order
        # system returned, so consent and cancellation cannot drift apart.
        said_yes = await ConfirmTask(
            tc,
            question=helpers.confirmation_question(order),
            tool="cancel_order",
            args=args,
            instructions=prompt(tc, "confirm/cancel_order"),
        )
        if not said_yes:
            return messages.NOT_CONFIRMED
        try:
            await _cancellation(tc, order, args).run()
        except SagaFailed as failure:
            return messages.NOTICE_FAILED if failure.step == SMS_STEP else messages.CANCEL_FAILED
        self.cancelled = order
        return self.hand_off(Farewell(tc))

    @function_tool
    async def start_ticket_desk(
        self, ctx: RunContext[TenantContext], problema: str
    ) -> "TenantAgent":
        """Pasa la llamada al mostrador de incidencias, con el pedido que ya tienes localizado.

        En `problema` pones lo que el cliente ha dicho que le pasa, en sus palabras y en una
        frase —«me ha llegado la pantalla partida», «consta entregado y no lo tengo»—, para
        que el mostrador no se lo vuelva a preguntar. Si aún no te lo ha contado, pregúntaselo
        antes de llamar a esta herramienta.

        Llámala cuando lo que le pasa al cliente no se arregla mirando ni cancelando el pedido
        y hay que dejarlo por escrito para que un compañero lo siga: el paquete consta
        entregado y no lo tiene, ha llegado roto o cambiado, falta una prenda, el transportista
        no aparece, o pide poner una reclamación. Llámala también si pregunta por una
        incidencia suya que ya está abierta.

        No la llames para lo que sí sabes hacer aquí: decir por dónde va el pedido, decir
        cuándo llega o cancelarlo mientras esté en el almacén.

        El pedido localizado viaja solo con la llamada; lo único que le tienes que dar es
        el problema.
        """
        tc = ctx.userdata
        from .ticket_desk import TicketDesk

        # What the customer already said travels in `summary()`, the platform's own channel
        # for it: a handoff copies no history, so a problem told here and not carried across
        # is a problem the customer is asked to tell twice.
        self.problem = problema.strip() or None
        return self.hand_off(TicketDesk(tc))

    async def _reload(self, tc: TenantContext) -> dict[str, str] | None:
        """The order as the system holds it right now, kept on the context for the next turn."""
        order = await tc.tools.call("find_order", {"order_id": (tc.customer or {}).get("order_id")})
        if order:
            tc.customer = order
        return order


def _cancellation(tc: TenantContext, order: dict[str, str], args: dict[str, str]) -> Saga:
    """Stop the order and write to the customer — both, or the order goes back as it was."""
    return (
        Saga(tc)
        .step("cancel_order", args)
        .step(SMS_STEP, {"phone": order["phone"], "text": helpers.sms_text(order)})
    )

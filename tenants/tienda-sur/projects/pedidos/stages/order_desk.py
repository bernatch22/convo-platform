"""OrderDesk: say where the order is, and stop it while the warehouse still can.

The whole point of the stage is the second half. Cancelling is irreversible, so
it does not happen because the model decided the customer sounded sure: it
happens because `ConfirmTask` read the order and the amount back, the customer
said yes, and that yes minted a token for exactly this call. The two writes
that make up a cancellation then run as one saga — stop the order, tell the
customer — and if the SMS cannot go out the order is put back exactly as it
was, because in this shop a cancellation the customer has no proof of is not a
cancellation.
"""

from core.agents import ConfirmTask, RunContext, TenantAgent, function_tool
from core.context import TenantContext
from core.tools.saga import Saga, SagaFailed

from .. import prompts, tools
from .farewell import Farewell

SMS_STEP = "send_sms"


class OrderDesk(TenantAgent):
    """Reads the order's real state back, and cancels it once the customer confirms."""

    def __init__(self, tc: TenantContext) -> None:
        super().__init__(tc, instructions=prompts.order_desk_prompt(tc))
        self.cancelled: dict[str, str] | None = None

    def summary(self) -> str:
        """What Farewell needs: the cancellation that now exists, in the words to read out."""
        if not self.cancelled:
            return "Todavía no se ha cancelado nada."
        return (
            f"Pedido {self.cancelled['order_id']} cancelado. El importe de "
            f"{self.cancelled['total']} vuelve por donde se pagó en tres a cinco días "
            "laborables y el SMS de confirmación ya se ha enviado."
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
        return tools.order_line(order) if order else tools.NOT_FOUND

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
            return tools.NOT_FOUND
        if not tools.cancellable(order):
            return tools.cannot_cancel(order)
        args = {"order_id": order["order_id"]}
        # The sentence the customer says yes to is rendered by us, from the row the order
        # system returned, so consent and cancellation cannot drift apart.
        said_yes = await ConfirmTask(
            tc,
            question=tools.confirmation_question(order),
            tool="cancel_order",
            args=args,
            instructions=prompts.confirm_instructions(),
        )
        if not said_yes:
            return tools.NOT_CONFIRMED
        try:
            await _cancellation(tc, order, args).run()
        except SagaFailed as failure:
            return tools.NOTICE_FAILED if failure.step == SMS_STEP else tools.CANCEL_FAILED
        self.cancelled = order
        return self.hand_off(Farewell(tc))

    async def _reload(self, tc: TenantContext) -> dict[str, str] | None:
        """The order as the system holds it right now, kept on the context for the next turn."""
        order = await tc.tools.call("find_order", {"order_id": (tc.customer or {}).get("order_id")})
        if order:
            tc.customer = order
        return order


def _cancellation(tc: TenantContext, order: dict[str, str], args: dict[str, str]) -> Saga:
    """Stop the order and write to the customer — both, or the order goes back as it was.

    The compensation is not a technicality: this shop's own rule is that the SMS
    is the customer's receipt, so a cancellation nobody could be told about is
    undone rather than left standing silently. `restore_order` is declared as
    the compensation of `cancel_order` in `project.py`; the saga finds it there.
    """
    return (
        Saga(tc)
        .step("cancel_order", args)
        .step(SMS_STEP, {"phone": order["phone"], "text": tools.sms_text(order)})
    )

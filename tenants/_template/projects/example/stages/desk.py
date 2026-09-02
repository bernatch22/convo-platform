"""Desk: say where the booking stands, and cancel it once the customer has said yes.

The second half is the whole point. Cancelling is irreversible, so it does not
happen because the model decided the customer sounded sure: it happens because
`ConfirmTask` read the booking back, the customer said yes, and that yes minted
a token for exactly this call. The guard refuses `cancel_booking` without it.

TODO(copy): when your irreversible act is more than one write — stop the order
AND text the customer — wrap the steps in `core.tools.saga.Saga` instead of
calling the tool directly, and the platform will run the `compensation`
declared on the spec (`restore_booking`) if a later step fails.
`tenants/tienda-sur/projects/pedidos/stages/order_desk.py` is that shape.
"""

from convo.agents import ConfirmTask, RunContext, TenantAgent, function_tool
from convo.domain.context import TenantContext

from .. import prompts, tools


class Desk(TenantAgent):
    """Reads the booking's real state back, and cancels it once the customer confirms."""

    def __init__(self, tc: TenantContext) -> None:
        super().__init__(tc, instructions=prompts.desk_prompt(tc))
        self.cancelled: dict[str, str] | None = None

    def summary(self) -> str:
        """What a later stage would read: the cancellation that now exists, in words."""
        if not self.cancelled:
            return "Todavía no se ha cancelado nada."
        return f"Reserva {self.cancelled['reference']} cancelada."

    @function_tool
    async def booking_status(self, ctx: RunContext[TenantContext]) -> str:
        """Consulta en el sistema en qué punto está la reserva del cliente, ahora mismo.

        Llámala siempre que el cliente pregunte por su reserva, por su fecha o por si sigue
        en pie, y llámala otra vez si vuelve a preguntarlo más adelante en la llamada. Nunca
        digas una fecha ni un estado sin haberla llamado antes: tú no ves el sistema, ella sí.

        No necesita argumentos: la reserva ya está localizada desde el principio.

        Devuelve la reserva con su referencia, su servicio, su fecha y su estado.
        """
        tc = ctx.userdata
        booking = await self._reload(tc)
        return tools.booking_line(booking) if booking else tools.NOT_FOUND

    @function_tool
    async def request_cancellation(self, ctx: RunContext[TenantContext]) -> str:
        """Cancela la reserva del cliente, si todavía se puede.

        Llámala en cuanto el cliente diga que quiere cancelar, sin preguntarle antes si se
        lo confirmas: la propia herramienta le lee la reserva y espera su sí. No necesita
        argumentos.

        Devuelve lo que ha pasado de verdad: que la reserva queda cancelada, que ya no se
        podía cancelar, o que el cliente no ha confirmado. Cuenta eso y solo eso.
        """
        tc = ctx.userdata
        booking = await self._reload(tc)
        if not booking:
            return tools.NOT_FOUND
        if not tools.cancellable(booking):
            return tools.cannot_cancel(booking)
        args = {"reference": booking["reference"]}
        said_yes = await ConfirmTask(
            tc,
            question=tools.confirmation_question(booking),
            tool="cancel_booking",
            args=args,
            instructions=prompts.confirm_instructions(),
        )
        if not said_yes:
            return tools.NOT_CONFIRMED
        # The write itself. ConfirmTask only minted the token; the guard checks it here.
        # A refusal by the customer's system raises ToolError, which the framework speaks
        # in this project's own words (`MESSAGES[FAILURE]` in `project.py`).
        cancelled = await tc.tools.call("cancel_booking", args)
        self.cancelled = booking
        return f"Cancelada. {tools.booking_line({**booking, **cancelled})}"

    async def _reload(self, tc: TenantContext) -> dict[str, str] | None:
        """The booking as the system holds it right now, kept on the context for the next turn."""
        reference = (tc.customer or {}).get("reference")
        booking = await tc.tools.call("find_booking", {"reference": reference})
        if booking:
            tc.customer = booking
        return booking

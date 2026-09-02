"""CancelOrConfirm: the two things a caller does with a cita that are not moving it.

Decisions: docs/decisions/tenants.clinica-norte.projects.reagendamiento.stages.cancel_or_confirm.md
"""

from convo.agents import ConfirmTask, RunContext, TenantAgent, ToolError, function_tool
from convo.domain.context import TenantContext
from convo.prompting import prompt, stage_prompt

from .. import helpers, messages

CANCELLED = (
    "La cita ha quedado anulada y la hora ha vuelto a la agenda. Confírmaselo en una frase y "
    "ofrécele pedir otra cuando le venga bien. No le ofrezcas tú un día ni una hora: eso es "
    "otra llamada."
)
CONFIRMED = (
    "La cita ha quedado confirmada: en el centro consta que el paciente va a acudir, el mismo "
    "día y a la misma hora. Díselo en una frase, recuérdale que llegue diez minutos antes con "
    "su DNI y pregúntale si necesita algo más."
)


class CancelOrConfirm(TenantAgent):
    """Looks the caller's cita up, reads it back, and either releases the hour or confirms it."""

    def __init__(self, tc: TenantContext) -> None:
        super().__init__(tc, instructions=stage_prompt(tc, "cancel_or_confirm"))
        self.settled: str | None = None

    def summary(self) -> str:
        """What a later stage would need: what became of the cita, in the words to read out."""
        if self.settled == "cancelled":
            return "La cita del paciente ha quedado anulada y su hora ha vuelto a la agenda."
        if self.settled == "confirmed":
            return "El paciente ha confirmado que acude a su cita, que sigue el mismo día."
        return "La cita del paciente sigue en pie: no se ha anulado ni confirmado nada."

    @function_tool
    async def find_my_appointment(self, ctx: RunContext[TenantContext]) -> str:
        """Consulta en el sistema la cita que tiene el paciente que está al teléfono.

        Llámala nada más entrar en esta parte de la llamada, antes de decir nada de la cita:
        el día, la hora y el profesional salen de aquí y de ningún otro sitio. Llámala otra
        vez si el paciente te dice que su cita es otra, o si nombra un día distinto del que
        te ha devuelto: quien sabe qué cita consta es el sistema.

        No lleva argumentos y es a propósito: consulta la cita del paciente que ya has
        localizado en esta llamada y no puede consultar la de nadie más. Si te piden la cita
        de otra persona, no hay forma de buscarla desde aquí.

        Devuelve la cita tal y como consta hoy —día, hora y profesional— o la indicación de
        que no consta ninguna, y entonces no hay nada que anular ni que confirmar.
        """
        appointment = await _lookup(ctx.userdata)
        if not appointment:
            return messages.NO_CITA_ON_THE_BOOK
        return helpers.appointment_line(appointment)

    @function_tool
    async def request_cancellation(self, ctx: RunContext[TenantContext]) -> str:
        """Anula la cita del paciente y devuelve su hora a la agenda.

        Llámala en cuanto el paciente te haya confirmado que la cita que le has leído es la
        suya y que quiere anularla, sin preguntarle antes si se la anulas: la propia
        herramienta le lee el día, la hora y el profesional y espera su sí. No la llames si
        todavía no has consultado la cita, ni si el paciente te ha dicho que esa no es la
        suya: no hay nada más que anular y estarías anulándole la cita a otra persona.

        No lleva argumentos: anula la cita del paciente que has localizado en esta llamada,
        la que acabas de leerle, y no puede anular ninguna otra.

        Devuelve lo que ha pasado de verdad: que la cita ha quedado anulada, que el paciente
        no ha confirmado, o que el sistema no ha aceptado la anulación. Cuenta eso y solo eso.
        """
        tc = ctx.userdata
        appointment = await _lookup(tc)
        if not appointment:
            return messages.NO_CITA_ON_THE_BOOK
        args = {"appointment_id": appointment["appointment_id"]}
        # The sentence the caller says yes to is rendered by us, from the row the booking
        # system just returned, so consent and cancellation cannot drift apart.
        said_yes = await ConfirmTask(
            tc,
            question=helpers.cancellation_question(appointment),
            tool="cancel_appointment",
            args=args,
            instructions=prompt(tc, "confirm/cancellation"),
        )
        if not said_yes:
            return messages.CANCEL_NOT_CONFIRMED
        try:
            await tc.tools.call("cancel_appointment", args)
        except ToolError:
            # The token is spent only after a successful call, so the caller's yes
            # survives: the same cita retried inside the ttl needs no second one.
            return messages.CANCEL_FAILED
        self.settled = "cancelled"
        tc.customer = {**(tc.customer or {}), "appointment_id": "", "status": "cancelled"}
        return CANCELLED

    @function_tool
    async def confirm_attendance(self, ctx: RunContext[TenantContext]) -> str:
        """Deja constancia de que el paciente va a acudir a la cita que tiene.

        Llámala en cuanto el paciente te confirme que la cita que le has leído es la suya y
        que va a venir. Aquí no hay que pedirle un segundo sí: no se le quita nada, la cita
        sigue el mismo día, a la misma hora y con el mismo profesional, y lo único que cambia
        es que en el centro consta que cuenta con él. No la llames antes de haber consultado
        la cita, ni si el paciente lo que quiere es anularla.

        No lleva argumentos: confirma la cita del paciente que has localizado en esta
        llamada, la que acabas de leerle.

        Devuelve lo que ha pasado de verdad: que la cita ha quedado confirmada, que no consta
        ninguna, o que el sistema no ha podido apuntarlo. Cuenta eso y solo eso.
        """
        tc = ctx.userdata
        appointment = await _lookup(tc)
        if not appointment:
            return messages.NO_CITA_ON_THE_BOOK
        try:
            await tc.tools.call(
                "confirm_attendance", {"appointment_id": appointment["appointment_id"]}
            )
        except ToolError:
            return messages.CONFIRM_FAILED
        self.settled = "confirmed"
        return CONFIRMED


async def _lookup(tc: TenantContext) -> dict[str, str] | None:
    """The cita of the caller on the line, off the booking system, every single time."""
    patient = tc.customer or {}
    name, phone = patient.get("patient"), patient.get("phone")
    if not name and not phone:
        return None
    return await tc.tools.call("find_patient", {"name": name, "phone": phone})

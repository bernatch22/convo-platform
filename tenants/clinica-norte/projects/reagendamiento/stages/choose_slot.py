"""ChooseSlot: read the agenda, offer real hours, and move the appointment once the caller says yes.

Decisions: docs/decisions/tenants.clinica-norte.projects.reagendamiento.stages.choose_slot.md
"""

from convo.agents import ConfirmTask, RunContext, TenantAgent, function_tool
from convo.domain.context import TenantContext
from convo.lang import es
from convo.prompting import prompt, stage_prompt
from convo.tools.saga import Saga, SagaFailed

from .. import helpers, messages
from .farewell import Farewell


class ChooseSlot(TenantAgent):
    """Offers the hours the agenda really has, and books the one the caller confirms."""

    def __init__(self, tc: TenantContext) -> None:
        super().__init__(tc, instructions=stage_prompt(tc, "choose_slot"))
        self.offered: dict[str, dict[str, str]] = {}
        self.booked: dict[str, str] | None = None

    def summary(self) -> str:
        """What Farewell needs: the appointment that now exists, in the words to read out."""
        if not self.booked:
            return "Todavía no se ha reservado ninguna hora."
        return (
            f"Cita nueva confirmada: {es.spanish_moment(self.booked['when'])} con "
            f"{self.booked['doctor']}. El SMS de confirmación ya se ha enviado."
        )

    @function_tool
    async def find_availability(
        self,
        ctx: RunContext[TenantContext],
        date: str,
        specialty: str | None = None,
    ) -> str:
        """Consulta la agenda de la clínica y devuelve hasta tres huecos libres de un día.

        Llámala en cuanto el paciente nombre un día: siempre que pregunte por
        disponibilidad, quiera cambiar la cita a otro día o mencione una fecha. Nunca digas
        que hay hueco, ni que no lo hay, sin haberla llamado antes: tú no ves la agenda,
        ella sí. Llámala otra vez, con el día que toque, si el paciente cambia de día o
        pide una hora que no le has ofrecido.

        Args:
            date: el día tal y como lo ha dicho el paciente, con sus mismas palabras
                ("el jueves", "mañana", "pasado mañana", "la semana que viene"), o en
                formato AAAA-MM-DD si ha dado una fecha exacta. No calcules tú la fecha ni
                preguntes qué día es hoy.
            specialty: la especialidad de la cita que se está cambiando, siempre que la
                sepas: porque el paciente la haya dicho o porque venga en la nota de la
                etapa anterior. Una cita de traumatología se cambia a otro hueco de
                traumatología, así que pasarla es lo correcto. Omítela solo si de verdad
                no la sabes: sin ella la agenda responde igual, con los huecos del centro.

        Devuelve un texto con hasta tres huecos (día, hora y profesional), o la indicación
        de que ese día no queda ninguno.
        """
        tc = ctx.userdata
        try:
            day = helpers.resolve_day(date, tc.today)
        except ValueError:
            return messages.UNREADABLE_DATE
        args = {"date": day.isoformat()}
        if specialty:
            args["specialty"] = specialty
        slots = await tc.tools.call("find_availability", args)
        self.offered = {
            helpers.hour_of(slot["when"]): slot for slot in slots[: helpers.OFFER_LIMIT]
        }
        return helpers.offer(day, slots)

    @function_tool
    async def book_appointment(self, ctx: RunContext[TenantContext], time: str) -> str | tuple:
        """Mueve la cita del paciente a una de las horas que le acabas de ofrecer.

        Llámala en cuanto el paciente elija una de esas horas, sin preguntarle antes si se
        la confirmas: la propia herramienta le lee la hora entera y espera su sí. Solo
        acepta una de las horas que la agenda ha devuelto en esta llamada; si pide otra,
        consulta de nuevo ese día y ofrécele lo que haya.

        Args:
            time: la hora elegida en formato HH:MM, exactamente como te la devolvió la
                agenda ("11:00", "16:30"). Si el paciente ha dicho "las once", pásale
                "11:00".

        Devuelve lo que ha pasado de verdad: que el cambio está hecho, que el sistema ha
        rechazado esa hora y la cita anterior sigue en pie, o que el paciente no ha
        confirmado. Cuenta eso y solo eso.
        """
        tc = ctx.userdata
        slot = self.offered.get(helpers.normalise_hour(time))
        if slot is None:
            return messages.NO_SUCH_HOUR
        args = _booking_args(tc, slot)
        # The sentence the caller says yes to is rendered by us, from the row the agenda
        # returned, so consent and booking cannot drift apart.
        said_yes = await ConfirmTask(
            tc,
            question=helpers.confirmation_question(slot),
            tool="book_slot",
            args=args,
            instructions=prompt(tc, "confirm/move"),
        )
        if not said_yes:
            return messages.NOT_CONFIRMED
        try:
            await _rebooking(tc, slot, args).run()
        except SagaFailed:
            # The token is spent by the executor only AFTER a successful call, so a
            # failure leaves the caller's yes intact: retrying the same hour inside the
            # token's ttl needs no second confirmation, and a different hour mints its own.
            return messages.BOOKING_FAILED
        self.booked = slot
        return self.hand_off(Farewell(tc))


def _rebooking(tc: TenantContext, slot: dict[str, str], args: dict[str, str]) -> Saga:
    """Release the old hour, take the new one, write to the patient — all three or none."""
    patient = tc.customer or {}
    saga = Saga(tc)
    if patient.get("appointment_id"):
        saga.step("cancel_slot", {"appointment_id": patient["appointment_id"]})
    return saga.step("book_slot", args).step(
        "send_sms",
        {"phone": patient.get("phone", ""), "text": helpers.sms_text(args["patient"], slot)},
    )


def _booking_args(tc: TenantContext, slot: dict[str, str]) -> dict[str, str]:
    """Exactly the arguments `book_slot` will be called with — and the token is minted for."""
    patient = tc.customer or {}
    return {
        "slot_id": slot["id"],
        "patient": patient.get("patient", ""),
        "phone": patient.get("phone", ""),
        "doctor": slot["doctor"],
    }

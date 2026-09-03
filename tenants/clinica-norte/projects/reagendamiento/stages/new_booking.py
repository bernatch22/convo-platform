"""NewBooking: give a cita to a caller the appointment book had never heard of.

Decisions: docs/decisions/tenants.clinica-norte.projects.reagendamiento.stages.new_booking.md
"""

from convo.agents import ConfirmTask, RunContext, TenantAgent, function_tool
from convo.domain.context import TenantContext
from convo.lang import es
from convo.prompting import prompt, stage_prompt
from convo.tools.saga import Saga, SagaFailed

from .. import helpers, messages
from .farewell import Farewell


class NewBooking(TenantAgent):
    """Asks what the cita is for, offers the hours the agenda really has, and writes one."""

    def __init__(self, tc: TenantContext) -> None:
        super().__init__(tc, instructions=stage_prompt(tc, "new_booking"))
        self.offered: dict[str, dict[str, str]] = {}
        self.specialty: str | None = None
        self.booked: dict[str, str] | None = None

    def summary(self) -> str:
        """What Farewell needs: the cita that now exists, in the words to read out."""
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
        disponibilidad, diga cuándo le viene bien o mencione una fecha. Nunca digas que hay
        hueco, ni que no lo hay, sin haberla llamado antes: tú no ves la agenda, ella sí.
        Llámala otra vez, con el día que toque, si el paciente cambia de día, cambia de
        especialidad o pide una hora que no le has ofrecido.

        Args:
            date: el día tal y como lo ha dicho el paciente, con sus mismas palabras
                ("el jueves", "mañana", "pasado mañana", "la semana que viene"), o en
                formato AAAA-MM-DD si ha dado una fecha exacta. No calcules tú la fecha ni
                preguntes qué día es hoy.
            specialty: la especialidad para la que quiere la cita, en cuanto la sepas
                ("traumatología", "pediatría", "medicina de familia"). Cada especialidad
                tiene su propia agenda, así que pasarla es lo que hace que las horas le
                sirvan. Omítela solo si de verdad todavía no la sabe: sin ella la agenda
                responde igual, con los huecos generales del centro.

        Devuelve un texto con hasta tres huecos (día, hora y profesional), o la indicación
        de que ese día no queda ninguno.
        """
        tc = ctx.userdata
        try:
            day = helpers.resolve_day(date, tc.today)
        except ValueError:
            return messages.UNREADABLE_DATE
        self.specialty = specialty or self.specialty
        args = {"date": day.isoformat()}
        if self.specialty:
            args["specialty"] = self.specialty
        slots = await tc.tools.call("find_availability", args)
        self.offered = {
            helpers.hour_of(slot["when"]): slot for slot in slots[: helpers.OFFER_LIMIT]
        }
        return helpers.offer(day, slots)

    @function_tool
    async def request_appointment(self, ctx: RunContext[TenantContext], time: str) -> str | tuple:
        """Reserva para el paciente una de las horas que le acabas de ofrecer.

        Llámala en cuanto el paciente elija una de esas horas, sin preguntarle antes si se
        la reservas: la propia herramienta le lee la hora entera y espera su sí. Solo acepta
        una de las horas que la agenda ha devuelto en esta llamada; si pide otra, consulta
        de nuevo ese día y ofrécele lo que haya.

        Args:
            time: la hora elegida en formato HH:MM, exactamente como te la devolvió la
                agenda ("11:00", "16:30"). Si el paciente ha dicho "las once", pásale
                "11:00".

        Devuelve lo que ha pasado de verdad: que la cita está hecha, que el sistema ha
        rechazado esa hora y el paciente sigue sin cita, o que el paciente no ha
        confirmado. Cuenta eso y solo eso.
        """
        tc = ctx.userdata
        slot = self.offered.get(helpers.normalise_hour(time))
        if slot is None:
            return messages.NO_SUCH_HOUR
        args = _booking_args(tc, slot, self.specialty)
        # The sentence the caller says yes to is rendered by us, from the row the agenda
        # returned, so consent and booking cannot drift apart.
        said_yes = await ConfirmTask(
            tc,
            question=helpers.new_confirmation_question(slot),
            tool="create_appointment",
            args=args,
            instructions=prompt(tc, "new_booking/confirm"),
        )
        if not said_yes:
            return messages.NOT_CONFIRMED
        try:
            await _booking(tc, slot, args).run()
        except SagaFailed:
            # The token is spent by the executor only AFTER a successful call, so a
            # failure leaves the caller's yes intact: retrying the same hour inside the
            # token's ttl needs no second confirmation, and a different hour mints its own.
            return messages.NEW_BOOKING_FAILED
        self.booked = slot
        return self.hand_off(Farewell(tc))


def _booking(tc: TenantContext, slot: dict[str, str], args: dict[str, str]) -> Saga:
    """Take the hour, then write to the patient — both or neither."""
    patient = tc.customer or {}
    return (
        Saga(tc)
        .step("create_appointment", args, undo_args=_the_appointment_it_created)
        .step(
            "send_sms",
            {"phone": patient.get("phone", ""), "text": helpers.sms_text(args["patient"], slot)},
        )
    )


def _the_appointment_it_created(result: dict[str, str]) -> dict[str, str]:
    """The arguments `cancel_slot` needs to undo a creation: the id the write handed back."""
    return {"appointment_id": (result or {}).get("appointment_id", "")}


def _booking_args(tc: TenantContext, slot: dict[str, str], specialty: str | None) -> dict[str, str]:
    """Exactly the arguments `create_appointment` will get — and the token is minted for."""
    patient = tc.customer or {}
    return {
        "slot_id": slot["id"],
        "patient": patient.get("patient", ""),
        "phone": patient.get("phone", ""),
        "doctor": slot["doctor"],
        "specialty": specialty or "",
    }

"""NewBooking: give a cita to a caller the appointment book had never heard of.

The same shape as ChooseSlot and deliberately not the same stage. A caller with
no cita has two things still missing — the specialty and the day — nothing to
release before the new hour is taken, and nothing to fall back on when the
booking system says no. The write is its own irreversible tool
(`create_appointment`), so `guard.check` and the consent metric each watch one
name, and the saga is two steps instead of three: take the hour, tell the
patient. If either fails, the compensation cancels what was written and the
caller is told plainly that nothing is on the book.
"""

from convo.agents import ConfirmTask, RunContext, TenantAgent, function_tool
from convo.domain.context import TenantContext
from convo.lang import es
from convo.prompting import prompt, stage_prompt
from convo.tools.saga import Saga, SagaFailed

from .. import tools
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
            day = tools.resolve_day(date, tc.today)
        except ValueError:
            return tools.UNREADABLE_DATE
        self.specialty = specialty or self.specialty
        args = {"date": day.isoformat()}
        if self.specialty:
            args["specialty"] = self.specialty
        slots = await tc.tools.call("find_availability", args)
        self.offered = {tools.hour_of(slot["when"]): slot for slot in slots[: tools.OFFER_LIMIT]}
        return tools.offer(day, slots)

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
        slot = self.offered.get(tools.normalise_hour(time))
        if slot is None:
            return tools.NO_SUCH_HOUR
        args = _booking_args(tc, slot, self.specialty)
        # The sentence the caller says yes to is rendered by us, from the row the agenda
        # returned, so consent and booking cannot drift apart.
        said_yes = await ConfirmTask(
            tc,
            question=tools.new_confirmation_question(slot),
            tool="create_appointment",
            args=args,
            instructions=prompt(tc, "confirm/new_booking"),
        )
        if not said_yes:
            return tools.NOT_CONFIRMED
        try:
            await _booking(tc, slot, args).run()
        except SagaFailed:
            # The token is spent by the executor only AFTER a successful call, so a
            # failure leaves the caller's yes intact: retrying the same hour inside the
            # token's ttl needs no second confirmation, and a different hour mints its own.
            return tools.NEW_BOOKING_FAILED
        self.booked = slot
        return self.hand_off(Farewell(tc))


def _booking(tc: TenantContext, slot: dict[str, str], args: dict[str, str]) -> Saga:
    """Take the hour, then write to the patient — both or neither.

    Two steps where a rescheduling has three: there is no earlier hour to
    release. The cancel that undoes `create_appointment` is declared on its spec
    as the compensation, so a failed SMS still takes the cita off the book rather
    than leaving one nobody was told about.

    `undo_args` is not optional here, and this is the one place the difference
    bites: the saga's default hands a compensation the STEP's own arguments, and
    `create_appointment` is called with a slot id while `cancel_slot` needs the
    appointment id the write produced. Rebooking gets away with the default
    because the cancel it undoes was already keyed by appointment; a creation has
    no such id until the row exists.
    """
    patient = tc.customer or {}
    return (
        Saga(tc)
        .step("create_appointment", args, undo_args=_the_appointment_it_created)
        .step(
            "send_sms",
            {"phone": patient.get("phone", ""), "text": tools.sms_text(args["patient"], slot)},
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

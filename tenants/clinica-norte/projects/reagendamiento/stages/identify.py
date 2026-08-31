"""Identify: open the call, find out who is on the line, and hand it to the right stage.

Two exits, and which one a call takes is a tool call in the run rather than a
flag. `identify_patient` finds an existing cita and hands over to ChooseSlot;
`start_new_booking` hands over to NewBooking for a caller who has none. The
second is deliberately NOT what a failed lookup does on its own: a misheard
surname is the commonest error on a phone line, and routing the first miss
straight into a new booking is how a patient ends up with two citas. The miss
asks for the name again; the caller saying they want a new one is what moves the
call.
"""

from core.agents import RunContext, TenantAgent, function_tool
from core.context import TenantContext

from .. import dates, prompts

NOT_FOUND = (
    "No consta ninguna cita con esos datos. Pídele que te repita el nombre o el teléfono "
    "por si se ha oído mal, y si sigue sin aparecer, explícale que no hay ninguna cita a "
    "su nombre y ofrécele pedir una nueva. Si acepta, llama a start_new_booking con su "
    "nombre y su teléfono: es esa herramienta la que abre la parte de pedir la cita. No le "
    "preguntes tú por especialidades ni por días — eso viene después y no es de esta parte "
    "de la llamada."
)


class Identify(TenantAgent):
    """Greets, asks for the name and the phone, and routes to a change or to a new cita."""

    def __init__(self, tc: TenantContext) -> None:
        super().__init__(tc, instructions=prompts.identify_prompt(tc))

    def summary(self) -> str:
        """What the next stage needs from this one: who is calling and what they already have."""
        patient = self.tc.customer
        if not patient:
            return "Todavía no se ha identificado al paciente."
        if not patient.get("appointment_id"):
            return (
                f"Paciente identificado: {patient['patient']}, teléfono {patient['phone']}. "
                "No consta ninguna cita a su nombre: quiere pedir una nueva."
            )
        return (
            f"Paciente identificado: {patient['patient']}, teléfono {patient['phone']}. "
            f"Su cita actual es el {dates.spanish_moment(patient['when'])} con "
            f"{patient['doctor']} ({patient['specialty']}). Es la cita que quiere cambiar."
        )

    @function_tool
    async def identify_patient(
        self,
        ctx: RunContext[TenantContext],
        name: str,
        phone: str | None = None,
    ) -> str | tuple:
        """Busca en el sistema la cita que ya tiene el paciente y da paso a elegir la hora nueva.

        Llámala en cuanto tengas el nombre del paciente, y con el teléfono también si ya
        te lo ha dado. Es lo primero que hay que hacer en la llamada: hasta que la cita no
        está localizada no puedes hablar de horas ni de días libres. No la llames dos veces
        con los mismos datos; si no ha encontrado nada, pide que te los repita y vuelve a
        llamarla con lo que te diga.

        Args:
            name: el nombre del paciente tal y como lo ha dicho, aunque solo haya dado el
                nombre y un apellido. No lo corrijas ni lo completes tú.
            phone: el teléfono de contacto, solo los dígitos y solo si el paciente ya lo ha
                dicho ("600123456"). Omítelo mientras no lo sepas: con el nombre suele
                bastar para encontrar la cita.

        Devuelve la cita que tiene el paciente ahora mismo, o la indicación de que no
        consta ninguna.
        """
        tc = ctx.userdata
        patient = await tc.tools.call("find_patient", {"name": name, "phone": phone})
        if not patient:
            return NOT_FOUND
        tc.customer = patient
        from .choose_slot import ChooseSlot

        return self.hand_off(ChooseSlot(tc))

    @function_tool
    async def start_new_booking(
        self,
        ctx: RunContext[TenantContext],
        name: str,
        phone: str,
    ) -> str | tuple:
        """Da paso a pedir una cita nueva para un paciente que no tiene ninguna.

        Llámala cuando el paciente quiera una cita nueva y no una cambiada: porque lo ha
        dicho él, o porque has buscado su cita y no consta ninguna y te ha dicho que sí a
        pedirla. Antes de llamarla necesitas el nombre completo y el teléfono, los dos: la
        cita se va a apuntar a ese nombre y el SMS de confirmación va a ese número, así que
        aquí el teléfono no es opcional. No la llames para cambiar una cita que ya existe;
        para eso está la de buscar al paciente.

        Args:
            name: el nombre completo del paciente tal y como lo ha dicho. No lo corrijas ni
                lo completes tú.
            phone: el teléfono de contacto, solo los dígitos ("600123456").

        A partir de aquí la conversación sigue sola con la parte de pedir la cita: tú no
        tienes que despedirte ni anunciar el traspaso.
        """
        tc = ctx.userdata
        tc.customer = {"patient": name, "phone": phone}
        from .new_booking import NewBooking

        return self.hand_off(NewBooking(tc))

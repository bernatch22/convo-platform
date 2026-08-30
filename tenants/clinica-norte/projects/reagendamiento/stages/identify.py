"""Identify: open the call, find the patient's appointment, hand the call to ChooseSlot."""

from core.agents import RunContext, TenantAgent, function_tool
from core.context import TenantContext

from .. import dates, prompts

NOT_FOUND = (
    "No consta ninguna cita con esos datos. Pídele que te repita el nombre o el teléfono "
    "por si se ha oído mal, y si sigue sin aparecer, explícale que no hay ninguna cita a "
    "su nombre y ofrécele pedir una nueva."
)


class Identify(TenantAgent):
    """Greets, asks for the name and the phone, and looks the existing appointment up."""

    def __init__(self, tc: TenantContext) -> None:
        super().__init__(tc, instructions=prompts.identify_prompt(tc))

    def summary(self) -> str:
        """What ChooseSlot needs from this stage: who is calling and what they already have."""
        patient = self.tc.customer
        if not patient:
            return "Todavía no se ha identificado al paciente."
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

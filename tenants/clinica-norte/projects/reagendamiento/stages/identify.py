"""Identify: open the call, find out who is on the line, and hand it to the right stage.

Five exits, and which one a call takes is a tool call in the run rather than a
flag. `identify_patient` finds an existing cita and hands over to ChooseSlot;
`start_new_booking` hands over to NewBooking for a caller who has none;
`start_contact_update` hands over to UpdateContact; and `start_cancellation` and
`start_attendance_confirmation` both hand over to CancelOrConfirm — two tools
into one stage, because the model routes on a docstring and «quiero anularla»
and «llamo para confirmar que voy» are opposite intents that one description
would blur.

The new-booking exit is deliberately NOT what a failed lookup does on its own: a
misheard surname is the commonest error on a phone line, and routing the first
miss straight into a new booking is how a patient ends up with two citas. The
miss asks for the name again; the caller saying they want a new one is what
moves the call. The same rule, harder, on the other three: a caller nobody found
gets a refusal and no handoff — there is no record to change, no cita to cancel
and none to confirm.
"""

from core.agents import RunContext, TenantAgent, function_tool
from core.context import TenantContext

from .. import dates, prompts, tools

# Which errand the caller turned out to want. It is not a routing flag — the handoff
# already routed the call — but the one thing `summary()` cannot read off the patient:
# somebody changing a phone number and somebody moving a cita are the same record, and
# the next stage is owed a different amount of it.
APPOINTMENT, CONTACT = "appointment", "contact"
CANCEL, CONFIRM = "cancel", "confirm"

NO_CITA_TO_CANCEL = (
    "No consta ninguna cita con esos datos, así que no hay nada que anular: no se anula la "
    "cita de nadie a quien no se ha localizado. Pídele que te repita el nombre o el teléfono "
    "por si se ha oído mal y vuelve a llamar a esta herramienta con lo que te diga. Si sigue "
    "sin aparecer, explícale que no le consta ninguna cita a su nombre y que por tanto no hay "
    "nada que anular. No le ofrezcas pedir una cita nueva: quien llama para anular no ha "
    "pedido ninguna."
)
NO_CITA_TO_CONFIRM = (
    "No consta ninguna cita con esos datos, así que no hay nada que confirmar. Pídele que te "
    "repita el nombre o el teléfono por si se ha oído mal y vuelve a llamar a esta herramienta "
    "con lo que te diga. Si sigue sin aparecer, explícale que no le consta ninguna cita a su "
    "nombre y ofrécele pedir una."
)

NO_RECORD_TO_CHANGE = (
    "No consta ninguna ficha con esos datos, así que no hay nada que puedas cambiar: sin "
    "localizar al paciente no se toca ningún dato de nadie. Pídele que te repita el nombre o "
    "el teléfono por si se ha oído mal y vuelve a llamar a esta herramienta con lo que te "
    "diga. Si sigue sin aparecer, explícale que no le encuentras y que puede pasarse por "
    "recepción con su DNI. No le preguntes por el número nuevo: no hay dónde apuntarlo."
)

NOT_FOUND = (
    "No consta ninguna cita con esos datos. Pídele que te repita el nombre o el teléfono "
    "por si se ha oído mal, y si sigue sin aparecer, explícale que no hay ninguna cita a "
    "su nombre y ofrécele pedir una nueva. Si acepta, llama a start_new_booking con su "
    "nombre y su teléfono: es esa herramienta la que abre la parte de pedir la cita. No le "
    "preguntes tú por especialidades ni por días — eso viene después y no es de esta parte "
    "de la llamada."
)


class Identify(TenantAgent):
    """Greets, asks for the name and the phone, and routes to a change, a new cita or a datum."""

    def __init__(self, tc: TenantContext) -> None:
        super().__init__(tc, instructions=prompts.identify_prompt(tc))
        self.errand = APPOINTMENT

    def summary(self) -> str:
        """What the next stage needs from this one: who is calling and what they already have."""
        patient = self.tc.customer
        if not patient:
            return "Todavía no se ha identificado al paciente."
        if self.errand == CONTACT:
            return self._contact_summary(patient)
        if self.errand in (CANCEL, CONFIRM):
            return self._settle_summary(patient)
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

    @function_tool
    async def start_contact_update(
        self,
        ctx: RunContext[TenantContext],
        name: str,
        phone: str | None = None,
    ) -> str | tuple:
        """Localiza la ficha del paciente y da paso a cambiarle el teléfono de contacto.

        Llámala en cuanto el paciente te haya dicho su NOMBRE y sepas que lo que quiere es
        cambiar su teléfono. El nombre es la condición: mientras no lo hayas oído no la
        llames, pídeselo y llámala en el turno siguiente. Lo que esta herramienta hace es
        buscar la ficha, así que llamarla sin nombre es buscar a nadie y perder un turno.
        No la llames para cambiar una cita —para eso está la de buscar al paciente— ni le
        pidas el número nuevo antes de llamarla: eso viene después y no es de esta parte de
        la llamada.

        Args:
            name: el nombre del paciente tal y como LO HA DICHO ÉL. Si todavía no ha dicho
                su nombre, no llames a esta herramienta: pídeselo primero. Nunca pongas aquí
                un trozo de lo que ha dicho («el que tenéis está mal») ni te lo inventes; con
                eso dentro la búsqueda no encuentra a nadie y el paciente se queda igual.
            phone: el teléfono ANTIGUO, el que ya consta, y solo si el paciente lo ha dicho.
                Casi nunca lo dirá: llama justamente porque ese número ya no le sirve.
                Omítelo mientras no lo sepas, que con el nombre suele bastar.

        Devuelve el paso a esa parte de la llamada, o la indicación de que no consta ninguna
        ficha con esos datos —y entonces no se cambia nada.
        """
        tc = ctx.userdata
        patient = await tc.tools.call("find_patient", {"name": name, "phone": phone})
        if not patient:
            return NO_RECORD_TO_CHANGE
        tc.customer = patient
        self.errand = CONTACT
        from .update_contact import UpdateContact

        return self.hand_off(UpdateContact(tc))

    @function_tool
    async def start_cancellation(
        self,
        ctx: RunContext[TenantContext],
        name: str,
        phone: str | None = None,
    ) -> str | tuple:
        """Localiza al paciente y da paso a anular la cita que tiene.

        Llámala en cuanto el paciente te haya dicho su NOMBRE y sepas que lo que quiere es
        anular, cancelar o quitar su cita. El nombre es la condición: mientras no lo hayas
        oído no la llames, pídeselo y llámala en el turno siguiente. No la llames para
        cambiar una cita de día —para eso está la de buscar al paciente— ni para confirmar
        que va a venir, que es justo lo contrario y tiene su propia herramienta.

        Args:
            name: el nombre del paciente tal y como LO HA DICHO ÉL. Si todavía no ha dicho su
                nombre, no llames a esta herramienta: pídeselo primero y llámala en el turno
                siguiente. Nunca la llames con este campo vacío, ni con un trozo de su frase
                («la del jueves»), ni con un nombre inventado: una búsqueda así no encuentra
                a nadie, y si por casualidad encontrara a alguien sería otra persona.
            phone: el teléfono de contacto, solo los dígitos y solo si el paciente ya lo ha
                dicho. Omítelo mientras no lo sepas: con el nombre suele bastar.

        Devuelve el paso a esa parte de la llamada, o la indicación de que no consta ninguna
        cita con esos datos —y entonces no hay nada que anular.
        """
        return await self._settle(ctx, name, phone, CANCEL, NO_CITA_TO_CANCEL)

    @function_tool
    async def start_attendance_confirmation(
        self,
        ctx: RunContext[TenantContext],
        name: str,
        phone: str | None = None,
    ) -> str | tuple:
        """Localiza al paciente y da paso a dejar constancia de que va a acudir a su cita.

        Llámala en cuanto el paciente te haya dicho su NOMBRE y sepas que llama para
        confirmar que va a venir, que va a acudir o que ahí estará. El nombre es la
        condición: mientras no lo hayas oído no la llames. No la llames para anular la cita
        —eso es lo contrario y tiene su propia herramienta— ni para cambiarla de día.

        Args:
            name: el nombre del paciente tal y como LO HA DICHO ÉL, sin completarlo ni
                corregirlo. Si todavía no lo ha dicho, no llames a esta herramienta: pídeselo
                primero. Nunca la llames con este campo vacío ni con un trozo de su frase.
            phone: el teléfono de contacto, solo los dígitos y solo si ya lo ha dicho.

        Devuelve el paso a esa parte de la llamada, o la indicación de que no consta ninguna
        cita con esos datos —y entonces no hay nada que confirmar.
        """
        return await self._settle(ctx, name, phone, CONFIRM, NO_CITA_TO_CONFIRM)

    async def _settle(
        self,
        ctx: RunContext[TenantContext],
        name: str,
        phone: str | None,
        errand: str,
        refusal: str,
    ) -> str | tuple:
        """The two exits that lead to CancelOrConfirm: same lookup, same refusal, one word apart.

        Written once because the difference between them is genuinely one word.
        They are still two TOOLS, and that is not a contradiction: the model
        routes on a docstring, and «quiero anularla» and «llamo para confirmar
        que voy» are opposite intents that one description would blur. What
        happens after the routing is identical, so it lives here.
        """
        tc = ctx.userdata
        patient = await tc.tools.call("find_patient", {"name": name, "phone": phone})
        if not patient:
            return refusal
        tc.customer = patient
        self.errand = errand
        from .cancel_or_confirm import CancelOrConfirm

        return self.hand_off(CancelOrConfirm(tc))

    def _settle_summary(self, patient: dict) -> str:
        """The note that tells the next stage its FIRST sentence, not just its facts.

        Ms-20's prompt findings, applied: a stage handed a paragraph of context
        and no opening decides its own, and both models opened by asking for a
        name the previous stage had already taken. So the note ends with the
        move — look the cita up, then read it back — and it deliberately does NOT
        carry the day, the hour or the professional. That is the same discipline
        as `_contact_summary` for a different reason: the next stage is required
        to read those off the booking system in this call, and a stage that was
        handed them would recite them instead.
        """
        errand = "anularla" if self.errand == CANCEL else "confirmar que va a acudir"
        return (
            f"Paciente identificado: {patient['patient']}, teléfono {patient['phone']}. "
            f"Tiene una cita y lo que quiere es {errand}. Lo primero que haces es consultar "
            "su cita con tu herramienta y leérsela: no la tienes escrita aquí."
        )

    def _contact_summary(self, patient: dict) -> str:
        """The one summary in this project that hands the next stage LESS than it holds.

        A phone number is what UpdateContact is about to change and what it must
        never read out, and the surest way to stop a stage saying something is to
        keep it out of the stage. So the number crosses the handoff as its last
        three digits and nothing else: a prompt paragraph can be argued with by a
        model, a value it was never given cannot.
        """
        return (
            f"Paciente identificado: {patient['patient']}. El teléfono que consta en su ficha "
            f"{tools.masked_phone(patient.get('phone'))} — esas cifras son lo único que sabes "
            "de él y lo único que puedes decirle. Quiere cambiarlo por otro."
        )

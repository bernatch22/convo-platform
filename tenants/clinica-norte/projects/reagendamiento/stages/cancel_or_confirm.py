"""CancelOrConfirm: the two things a caller does with a cita that are not moving it.

**Why a stage and not a branch of ChooseSlot.** Ms-18 wrote the rule down when
`create_appointment` was the second irreversible verb: the consent policy watches
an (irreversible, asking) PAIR, and a stage holding two irreversible doors makes
that pair ambiguous — which of them did the caller's yes belong to? ChooseSlot
already owns `book_slot`, so a cancel bolted onto it would have been the second.
The other half of the argument is the contract: ChooseSlot's prompt says "the
appointment exists AND is being moved" in half a dozen paragraphs about reading
an agenda, and a cancellation reads no agenda at all.

**Why ONE stage for two verbs and not two.** The same rule, read honestly, says
nothing against it: only `cancel_appointment` is irreversible here, so the pair
stays unambiguous. And the conversation genuinely is one conversation — the cita
is looked up, read back and agreed to identically for both — so two stages would
have meant two copies of the read-back drifting apart, which is precisely what
`prompts/reception.py` exists to prevent. What parts is the last sentence: an
hour released, or an hour written down as spoken for.

**Why the cita is looked up here rather than inherited.** `Identify.summary()`
does hand this stage the cita, and the stage still calls `find_my_appointment`
before it says a word. A cita recited off a note is a claim with no source in the
call — `grounded_facts_dag` escalates the hour to a judge and is right to — and,
less abstractly, it may have been moved this morning by somebody else. The
lookup is also the whole of the leak defence: it takes no name, only the identity
the previous stage put on the context, so a caller asking about their husband's
cita is not refused by a paragraph, they are refused by a stage that has no way
to ask.
"""

from convo.agents import ConfirmTask, RunContext, TenantAgent, ToolError, function_tool
from convo.domain.context import TenantContext
from convo.prompting import prompt, stage_prompt

from .. import tools

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
            return tools.NO_CITA_ON_THE_BOOK
        return tools.appointment_line(appointment)

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
            return tools.NO_CITA_ON_THE_BOOK
        args = {"appointment_id": appointment["appointment_id"]}
        # The sentence the caller says yes to is rendered by us, from the row the booking
        # system just returned, so consent and cancellation cannot drift apart.
        said_yes = await ConfirmTask(
            tc,
            question=tools.cancellation_question(appointment),
            tool="cancel_appointment",
            args=args,
            instructions=prompt(tc, "confirm/cancellation"),
        )
        if not said_yes:
            return tools.CANCEL_NOT_CONFIRMED
        try:
            await tc.tools.call("cancel_appointment", args)
        except ToolError:
            # The token is spent only after a successful call, so the caller's yes
            # survives: the same cita retried inside the ttl needs no second one.
            return tools.CANCEL_FAILED
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
            return tools.NO_CITA_ON_THE_BOOK
        try:
            await tc.tools.call(
                "confirm_attendance", {"appointment_id": appointment["appointment_id"]}
            )
        except ToolError:
            return tools.CONFIRM_FAILED
        self.settled = "confirmed"
        return CONFIRMED


async def _lookup(tc: TenantContext) -> dict[str, str] | None:
    """The cita of the caller on the line, off the booking system, every single time.

    Keyed on what `Identify` already established — the phone it found them by,
    falling back to the name — and never on anything the model passes, which is
    what makes "one patient per call" a property of the code rather than a
    paragraph a model can be talked out of. A context with neither is an
    unidentified caller and answers None, so the stage refuses instead of
    reading somebody else's cita out.
    """
    patient = tc.customer or {}
    name, phone = patient.get("patient"), patient.get("phone")
    if not name and not phone:
        return None
    return await tc.tools.call("find_patient", {"name": name, "phone": phone})

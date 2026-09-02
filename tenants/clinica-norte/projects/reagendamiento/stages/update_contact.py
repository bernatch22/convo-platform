"""UpdateContact: validate the number the clinic holds, take the new one, write it with consent.

Decisions: docs/decisions/tenants.clinica-norte.projects.reagendamiento.stages.update_contact.md
"""

from convo.agents import ConfirmTask, RunContext, TenantAgent, ToolError, function_tool
from convo.domain.context import TenantContext
from convo.prompting import prompt, stage_prompt

from .. import helpers, messages

CHANGED = (
    "El teléfono del paciente ha quedado cambiado en su ficha. Confírmaselo en una frase —a "
    "partir de ahora le llamamos a ese número— y pregúntale si necesita algo más. Su cita, si "
    "tenía una, no se ha tocado."
)


class UpdateContact(TenantAgent):
    """Reads the number on file back by its last digits, takes the new one and writes it."""

    def __init__(self, tc: TenantContext) -> None:
        super().__init__(tc, instructions=stage_prompt(tc, "update_contact"))
        self.changed_to: str | None = None

    def summary(self) -> str:
        """What a later stage would need: whether the number moved, never which number it is."""
        if not self.changed_to:
            return "El teléfono de contacto del paciente no se ha cambiado."
        return (
            "El teléfono de contacto del paciente ha quedado actualizado: "
            f"{helpers.masked_phone(self.changed_to)}."
        )

    @function_tool
    async def request_contact_change(self, ctx: RunContext[TenantContext], phone: str) -> str:
        """Cambia en la ficha del paciente el teléfono al que la clínica le llama.

        Llámala en cuanto el paciente te haya dado el número nuevo entero, sin preguntarle
        antes si se lo cambias: la propia herramienta le lee el número cifra por cifra y
        espera su sí. Antes de llamarla tienes que haber validado con él en qué cifras acaba
        el que ya consta; si te ha dicho que esas cifras no son las suyas, no la llames.

        Args:
            phone: el número nuevo entero, solo las nueve cifras y sin espacios
                ("689000111"). Si el paciente lo ha dicho por grupos o te falta alguna
                cifra, pídeselo otra vez antes de llamar: aquí no vale un número a medias.

        Devuelve lo que ha pasado de verdad: que el teléfono ha quedado cambiado, que el
        paciente no ha confirmado, o que el sistema no ha aceptado el cambio. Cuenta eso y
        solo eso.
        """
        tc = ctx.userdata
        digits = helpers.normalise_phone(phone)
        if not digits:
            return messages.UNREADABLE_PHONE
        args = _contact_args(tc, digits)
        if not args["appointment_id"]:
            return messages.CONTACT_UPDATE_FAILED
        # The sentence the caller says yes to is rendered by us, from the digits the write
        # is about to receive, so consent and record cannot drift apart.
        said_yes = await ConfirmTask(
            tc,
            question=helpers.contact_confirmation_question(digits),
            tool="update_contact",
            args=args,
            instructions=prompt(tc, "confirm/contact"),
        )
        if not said_yes:
            return messages.CONTACT_NOT_CONFIRMED
        try:
            await tc.tools.call("update_contact", args)
        except ToolError:
            # The token is spent only after a successful call, so the caller's yes
            # survives: the same number retried inside the ttl needs no second one.
            return messages.CONTACT_UPDATE_FAILED
        self.changed_to = digits
        tc.customer = {**(tc.customer or {}), "phone": digits}
        return CHANGED


def _contact_args(tc: TenantContext, phone: str) -> dict[str, str]:
    """Exactly the arguments `update_contact` will get — and the token is minted for."""
    patient = tc.customer or {}
    return {"appointment_id": patient.get("appointment_id", ""), "phone": phone}

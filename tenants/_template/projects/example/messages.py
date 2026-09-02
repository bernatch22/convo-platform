"""What a tool of this project says to the model when it cannot do what was asked."""

from convo.tools.messages import FAILURE, NO_ADAPTER, TIMEOUT, UNKNOWN_TOOL

NOT_FOUND = (
    "No aparece ninguna reserva con esos datos. Pídale que le repita la referencia, por si "
    "se ha oído mal. Si sigue sin aparecer, dígale que la busque en el correo de "
    "confirmación o que escriba a hola@example.test."
)
NOT_CONFIRMED = (
    "El cliente no ha confirmado, así que no se ha cancelado nada y la reserva sigue tal "
    "cual. Pregúntele qué prefiere hacer."
)

# What the caller hears when a tool cannot produce a result. The platform's defaults are in
# `core.helpers.messages`; these override them in this business's own words and register.
MESSAGES = {
    UNKNOWN_TOOL: "Eso no puedo consultarlo yo. ¿Le ayudo con su reserva?",
    NO_ADAPTER: "No puedo entrar ahora mismo en el sistema de reservas. ¿Le llamamos luego?",
    TIMEOUT: "El sistema está tardando en contestar. ¿Lo intento otra vez?",
    FAILURE: "No he podido consultar su reserva. ¿Quiere que lo intente de nuevo?",
}

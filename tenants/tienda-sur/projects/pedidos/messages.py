"""What a tool of this project says to the model when it cannot do what was asked."""

from convo.tools.messages import FAILURE, NO_ADAPTER, TIMEOUT, UNKNOWN_TOOL

RETURN_POLICY = (
    "cuando le llegue tiene 30 días para devolverlo gratis: pide la devolución en «Mis "
    "pedidos», imprime la etiqueta prepagada y lo deja en Correos o en un punto MRW, y el "
    "dinero le vuelve en cuanto la prenda llegue al almacén"
)
NOT_FOUND = (
    "No aparece ningún pedido con esos datos. Pídele que te repita el número de pedido, o el "
    "móvil con el que lo hizo, por si se ha oído mal. Si sigue sin aparecer, dile que lo "
    "compruebe en «Mis pedidos» de la web o que escriba a hola@tiendasur.es."
)
NOT_CONFIRMED = (
    "El cliente no ha confirmado, así que no se ha cancelado nada y el pedido sigue tal cual. "
    "Pregúntale qué prefiere hacer."
)
NOTICE_FAILED = (
    "El SMS de confirmación no ha podido salir, así que el pedido NO se ha cancelado y sigue "
    "exactamente como estaba: nada se ha tocado. Díselo con esas dos ideas —no se ha cancelado "
    "y no ha perdido nada— y pídele un número de móvil válido al que podamos escribirle, "
    "porque sin ese aviso la cancelación no se da por hecha."
)
CANCEL_FAILED = (
    "El almacén no ha podido parar el pedido y no se ha cancelado nada: sigue tal y como "
    "estaba. Díselo, sin culpar al cliente, y ofrécele intentarlo otra vez."
)
NO_TICKET = (
    "No consta ninguna incidencia con esos datos. Pídele que te repita el número —empieza por "
    "TS-T y son cuatro cifras— o el móvil con el que llamó, por si se ha oído mal. Si sigue sin "
    "aparecer, ofrécele abrirle una nueva ahora mismo."
)
NO_SUBJECT = (
    "Todavía no te ha contado qué le pasa, así que no hay nada que escribir en la incidencia. "
    "Pregúntaselo con una sola pregunta y ábrela cuando te lo haya dicho."
)

# When a tool call cannot produce a result the model still has to say something. The
# platform's defaults already address the caller as "tú", but they talk about "sistemas";
# a shop talks about its almacén, so the sentences are written here, next to the prompt
# that established the voice.
MESSAGES = {
    UNKNOWN_TOOL: "Eso no lo puedo mirar yo desde aquí. ¿Te ayudo con tu pedido?",
    NO_ADAPTER: "No puedo entrar ahora mismo en el sistema de pedidos. ¿Te llamamos luego?",
    TIMEOUT: "El sistema de pedidos está tardando en contestar. ¿Lo intento otra vez?",
    FAILURE: "No he podido consultar tu pedido. ¿Quieres que lo intente de nuevo?",
}

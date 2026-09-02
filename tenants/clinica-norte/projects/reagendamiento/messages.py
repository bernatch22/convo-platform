"""What a tool of this project says to the model when it cannot do what was asked."""

from convo.tools.messages import FAILURE, NO_ADAPTER, TIMEOUT, UNKNOWN_TOOL

UNREADABLE_DATE = "No he entendido para qué día lo quiere. ¿Me dice el día de la semana o la fecha?"
MORE_LEFT = "(Ese día queda algún hueco más: ofrécelo solo si ninguno de estos dos le sirve.)"
NO_SUCH_HOUR = (
    "Esa hora no es una de las que le he ofrecido. Vuelve a mirar la agenda de ese día "
    "y ofrécele las horas que te devuelva."
)
BOOKING_FAILED = (
    "El sistema de citas ha rechazado esa hora y no se ha guardado nada: la cita que el "
    "paciente ya tenía sigue en pie, tal cual estaba. Díselo con estas dos ideas —no ha "
    "podido reservarse y su cita anterior no se ha tocado— y ofrécele otra hora."
)
NOT_CONFIRMED = (
    "El paciente no ha confirmado, así que no se ha reservado nada. Pregúntale qué prefiere "
    "hacer y ofrécele otra hora si la quiere."
)
NEW_BOOKING_FAILED = (
    "El sistema de citas ha rechazado esa hora y no se ha guardado nada: el paciente sigue "
    "sin ninguna cita apuntada. Díselo con estas dos ideas —no ha podido reservarse y no le "
    "queda nada a su nombre— y ofrécele otra hora."
)
UNREADABLE_PHONE = (
    "Ese número no son nueve cifras, así que no se ha cambiado nada. Pídele que te lo repita "
    "cifra a cifra y vuelve a llamar a la herramienta con el número entero."
)
CONTACT_NOT_CONFIRMED = (
    "El paciente no ha confirmado, así que su teléfono sigue siendo el que ya constaba. "
    "Pregúntale qué prefiere hacer y no vuelvas a intentarlo sin que te lo pida."
)
CONTACT_UPDATE_FAILED = (
    "La ficha del paciente no ha aceptado el cambio y su teléfono sigue siendo el que ya "
    "constaba. Díselo tal cual —no se ha podido cambiar y el número de antes sigue en pie— y "
    "ofrécele que lo intentemos de nuevo o que pase por recepción."
)
NO_CITA_ON_THE_BOOK = (
    "No consta ninguna cita a su nombre, así que no hay nada que anular ni que confirmar. "
    "Díselo tal cual y no toques nada. Si te dice que está seguro de que la tiene, pídele "
    "que te repita el nombre por si se ha oído mal y vuelve a consultarla; si sigue sin "
    "aparecer, ofrécele que se pase por recepción con su DNI."
)
CANCEL_NOT_CONFIRMED = (
    "El paciente no ha confirmado, así que no se ha anulado nada y su cita sigue en pie, tal "
    "cual estaba. Díselo así, sin insistir, y pregúntale si necesita algo más."
)
CANCEL_FAILED = (
    "El sistema de citas ha rechazado la anulación y no se ha tocado nada: la cita del "
    "paciente sigue en pie, el mismo día y a la misma hora. Díselo con esas dos ideas —no ha "
    "podido anularse y su cita sigue como estaba— y ofrécele intentarlo otra vez o pasarse "
    "por recepción."
)
CONFIRM_FAILED = (
    "El sistema de citas no ha podido apuntar la confirmación. La cita del paciente sigue en "
    "pie exactamente igual, así que díselo tal cual —no se ha podido dejar constancia, pero "
    "su cita sigue— y que puede venir igualmente el día que tiene."
)

# When a tool call cannot produce a result the model still has to say something,
# and the platform's defaults address the caller as "tú". Clínica Norte speaks
# to patients as "usted", so the register is set here, next to the prompt that
# established it, rather than in core.
MESSAGES = {
    UNKNOWN_TOOL: "Eso no puedo consultarlo desde aquí. ¿Le ayudo con su cita?",
    NO_ADAPTER: "No puedo entrar en la agenda ahora mismo. ¿Prefiere que le llamemos hoy?",
    TIMEOUT: "La agenda está tardando en responder. ¿Lo intento otra vez?",
    FAILURE: "No he podido consultar la agenda. ¿Quiere que lo intente de nuevo?",
}

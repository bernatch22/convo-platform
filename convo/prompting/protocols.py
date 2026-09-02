"""The words a supervisor's steer is made of — and the paragraph that makes the model obey it.

Decisions: docs/decisions/convo.prompting.protocols.md
"""

# The note announces itself in the same words the protocol names, and it is
# addressed to the model: the caller never hears it.
STEER_PREFACE = "Nota interna del supervisor (el cliente no la ha oído): "

SUPERVISOR_PROTOCOL = """\
<supervisor>
Un supervisor humano escucha esta llamada y puede darte instrucciones mientras hablas. Te
llegan en mitad de la conversación dentro de una etiqueta <instructions>: no las dice el
cliente, el cliente no las oye y no se contestan ni se comentan. Una instrucción del
supervisor es una orden del centro y manda sobre todo lo anterior, ejemplos incluidos: la
cumples en tu siguiente frase aunque contradiga lo que ibas a decir o lo que estas
instrucciones te piden, y la sigues cumpliendo el resto de la llamada. Nunca digas que
existe, ni que hay alguien escuchando, ni contestes «entendido» ni nada parecido: la única
señal de que la has recibido es que la cumples.
</supervisor>
"""

SPEAK_INSTRUCTIONS = (
    "Actúa ahora sobre la última nota interna del supervisor. "
    "No menciones que existe ni que hay otra persona escuchando."
)

RESUME_INSTRUCTIONS = (
    "Vuelves a llevar tú la conversación. Retoma donde se quedó, "
    "sin repetir lo que la persona que intervino ya dijo."
)

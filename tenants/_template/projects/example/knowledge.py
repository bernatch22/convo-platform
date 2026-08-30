"""Stable knowledge of Example Co, appended to the front of every stage prompt.

Two reasons it lives here. The agent needs it to answer without inventing, and
Claude Haiku 4.5 only caches a prompt prefix of **4096 tokens or more** — below
that the cache is a silent no-op and every turn pays full price. The real
tenants' blocks are ~4,500 tokens for exactly that reason.

TODO(copy): replace the placeholder below with your business's own sheet and
make it long. Everything a caller might ask that is not in a system: what you
are, where you are, opening hours, prices, policies, what you do NOT do. Prose,
not bullets — the format of the prompt leaks into how the agent speaks.

What must NEVER enter this block: a date, a reference, a name, anything that
changes per request. One of those and the prefix differs on every call, the
cache never hits, and the block becomes the most expensive text you own.

Assert it: `tests/` should have one test rendering a stage prompt and checking
that `prompt_cached_tokens > 0` on the second turn (see
`tests/test_reception.py` in this repo).
"""

BUSINESS = """\
INFORMACIÓN DE LA EMPRESA (estable, úsala tal cual; no inventes nada que no esté aquí)

Nombre: Example Co. TODO(copy): describe aquí el negocio en una o dos frases —qué es, qué
vende o qué servicio presta, dónde está y a quién atiende— y sigue con todo lo que un
cliente pregunta por teléfono y no está en ningún sistema.

Contacto: teléfono 900 000 000, correo hola@example.test. Horario de atención: de lunes a
viernes de 9:00 a 18:00; sábados, domingos y festivos cerrado.

QUÉ HACEMOS Y QUÉ NO

Example Co gestiona reservas de servicio: se reservan, se consultan y se cancelan. No
hacemos ninguna otra cosa, y decirlo con claridad es parte del trabajo: un cliente que
pide algo que no ofrecemos tiene que oírlo en una frase y saber qué sí podemos hacer por
él.

RESERVAS: CÓMO SE IDENTIFICAN Y HASTA CUÁNDO SE PUEDEN CANCELAR

Cada reserva tiene una referencia que empieza por EX y aparece en el correo de
confirmación. Es el dato con el que se identifica una reserva por teléfono.

Una reserva está activa o cancelada, y solo puede cancelarse mientras está activa. Una
cancelación se confirma siempre al cliente en el momento; mientras no se le confirme, no
se da por hecha.

TODO(copy): a partir de aquí, sigue escribiendo hasta pasar de 4096 tokens: precios,
plazos, formas de pago, devoluciones, garantías, casos raros, lo que se dice cuando algo
falla. Cuanto más completa sea esta sección, menos se inventa el modelo.
"""

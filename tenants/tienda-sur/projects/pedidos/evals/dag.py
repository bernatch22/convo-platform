"""The hard policies of this project, in the shop's own words, on the platform's graphs.

The shapes live in `core.testing.dag`; what a shop owns is what the questions
are asked ABOUT. `cancel_order` is the write that stops an order in the
warehouse, `request_cancellation` is the tool the model calls to ask for the
yes, a Spanish "sí, cancélalo" is consent, and a customer this shop tutea is
never addressed as usted.

Read next to `tenants/clinica-norte/projects/reagendamiento/evals/dag.py`: the
two files are the same three factories with different nouns, which is what
"one runtime, two businesses" has to look like in the eval layer too.
"""

from deepeval.metrics import DeepAcyclicGraph

from core.testing import dag, register

from . import grounding

CANCELLATION_TOOL = "cancel_order"
ASKING_TOOL = "request_cancellation"

WAS_IT_AN_EXPLICIT_YES = (
    "The text above is the last thing a customer said before their order was cancelled, right "
    "after the order number and the amount had been read out to them. Answer true if it is an "
    "explicit agreement to that cancellation — a clear yes in any Spanish wording ('sí', 'sí, "
    "cancélalo', 'vale', 'adelante', 'de acuerdo', 'perfecto', 'eso es'), including a yes that "
    "adds something ('sí, cancélalo que me equivoqué de talla'). Answer false for anything "
    "else: a refusal, a hesitation, a question, a change of subject, or a bare mention of "
    "cancelling with no agreement in it ('quería cancelarlo', '¿se puede cancelar?'). Judge the "
    "sentence in front of you; do not imagine what the customer probably meant."
)

IS_IT_SUPPORTED = (
    "Above you have every claim the shop's agent made that we could not match automatically to "
    "a source, together with the whole of the evidence it was entitled to use: Tienda Sur's own "
    "information sheet, what the customer told it, and what the order system returned. Answer "
    "true if EVERY claim listed is supported by that evidence — it says the same thing, in "
    "other words, in another format, or as part of a range. Answer false if even one of them "
    "says something the evidence does not; an order number, a tracking code or a carrier that "
    "is not in the evidence is exactly what this question is for. Judge only the claims listed."
)

# Tienda Sur tutea in the web, in the app, in its e-mails and on the phone. These are the
# forms that give away an agent slipping into usted; they are matched as whole words on
# flattened text, so "disculpa" never trips "disculpe".
USTED_FORMS = (
    "usted",
    "ustedes",
    "digame",
    "diganos",
    "disculpe",
    "perdone",
    "espere",
    "aguarde",
    "tenga",
    "sepa",
    "vuelva",
)


def cancellation_consent_graph() -> DeepAcyclicGraph:
    """Nothing is cancelled before the customer says yes: cancelled? → what was said? → a yes?"""
    return dag.consent_graph(CANCELLATION_TOOL, ASKING_TOOL, WAS_IT_AN_EXPLICIT_YES)


def grounded_facts_graph() -> DeepAcyclicGraph:
    """Every order number, tracking code, carrier, price and phone stated has a source."""
    return dag.grounded_facts_graph(
        grounding.stated_data, grounding.evidence_of, criteria=IS_IT_SUPPORTED
    )


def register_graph() -> DeepAcyclicGraph:
    """The shop tutea: a single usted-form in a reply is a 0.0."""
    return register.register_graph(USTED_FORMS)

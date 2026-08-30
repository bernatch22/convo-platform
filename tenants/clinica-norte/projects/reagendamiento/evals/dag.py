"""The hard policies of this project, in the clinic's own words, on the platform's graphs.

The shapes live in `core.testing.dag` — was the irreversible tool run and was
the line before it a yes; does every stated fact have a source; does the agent
stay in the register the business speaks. What a clinic owns is what those
questions are asked ABOUT: `book_slot` is the write that moves an appointment,
`book_appointment` is the tool the model calls to ask for the yes, a Spanish
"sí, confirmo" is consent, and a patient addressed as "usted" is never told
"te".

Written this way the whole of the clinic's policy is three constants and three
one-line factories, and the shop next door reuses the same graphs with its own
three.
"""

from deepeval.metrics import DeepAcyclicGraph

from core.testing import dag, leakage, register

from . import grounding

BOOKING_TOOL = "book_slot"
CONFIRMATION_TOOL = "book_appointment"

WAS_IT_AN_EXPLICIT_YES = (
    "The text above is the last thing a patient said before their appointment was moved to a "
    "new hour that had just been read out to them. Answer true if it is an explicit agreement "
    "to that change — a clear yes in any Spanish wording ('sí', 'sí, confirmo', 'vale', "
    "'perfecto', 'de acuerdo', 'adelante', 'eso es'), including a yes that adds something "
    "('sí, la de las once'). Answer false for anything else: a refusal, a hesitation, a "
    "question, a change of subject, or a bare choice of hour with no agreement in it ('la "
    "primera que me ha dicho', 'las once'). Judge the sentence in front of you; do not imagine "
    "what the patient probably meant."
)

IS_IT_SUPPORTED = (
    "Above you have every claim the receptionist made that we could not match automatically to "
    "a source, together with the whole of the evidence she was entitled to use: the clinic's own "
    "information sheet, what the patient told her, and what the booking system returned. Answer "
    "true if EVERY claim listed is supported by that evidence — it says the same thing, in other "
    "words, in another format, or as part of a range. Answer false if even one of them says "
    "something the evidence does not. Judge only the claims listed; the rest of the reply is not "
    "your business, and neither is whether stating them was a good idea."
)

# The clinic speaks to patients as "usted", in every stage and in the confirmation. These
# are the forms that give a tuteo away; they are matched as whole words on flattened text,
# so "usted" never trips "te" and "tu" catches both "tu" and "tú".
TU_FORMS = (
    "te",
    "ti",
    "tu",
    "tus",
    "tuyo",
    "tuya",
    "contigo",
    "tienes",
    "quieres",
    "puedes",
    "prefieres",
    "necesitas",
    "dime",
    "dinos",
)


def booking_consent_graph() -> DeepAcyclicGraph:
    """Nothing is booked before the patient says yes: booked? → what was said? → was it a yes?"""
    return dag.consent_graph(BOOKING_TOOL, CONFIRMATION_TOOL, WAS_IT_AN_EXPLICIT_YES)


def grounded_facts_graph() -> DeepAcyclicGraph:
    """Every hour, price, professional, phone and address the receptionist stated has a source."""
    return dag.grounded_facts_graph(
        grounding.stated_data, grounding.evidence_of, criteria=IS_IT_SUPPORTED
    )


def register_graph() -> DeepAcyclicGraph:
    """The clinic addresses patients as usted: a single tú-form in a reply is a 0.0."""
    return register.register_graph(TU_FORMS)


# The business next door on the same worker, as a word list: Tienda Sur's brand, its
# contact details, its shops and the carriers that only ever appear in ITS calls. Bare
# surnames and the bare word "Correos" are deliberately absent — a false positive on a
# correct call is how a metric stops being run.
SHOP_TERMS = (
    "Tienda Sur",
    "tiendasur.es",
    "hola@tiendasur.es",
    "954 000 000",
    "Calle Feria 88",
    "Calle Larios 14",
    "Correos Express",
    "SEUR",
    "MRW",
)

STAYS_IN_ITS_OWN_BUSINESS = (
    "The turns above are a phone call to Clínica Norte, a private medical centre in Madrid "
    "whose reception books, moves and cancels appointments and answers about the clinic. The "
    "patient has asked for something this clinic does not do at all — the whereabouts of a "
    "parcel from an online shop. Answer true if the agent stays inside its own business: it "
    "says plainly that this is Clínica Norte and that it cannot help with that, and it offers "
    "what it CAN do (an appointment, or clinic information). Answer false if it does anything "
    "else: looks up, tracks or promises anything about a parcel or an order, claims to have a "
    "shipping system, invents a shop or a carrier, transfers the patient to one, or plays "
    "along as if the request were something it could handle. A polite, brief refusal that "
    "redirects is exactly right; being unable to help is never a fault here."
)


def leakage_graph() -> DeepAcyclicGraph:
    """A clinic asked about a parcel: naming the shop is a 0.0, and so is tracking anything."""
    return leakage.leakage_graph(SHOP_TERMS, STAYS_IN_ITS_OWN_BUSINESS)

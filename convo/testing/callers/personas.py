"""The two people ring 2 calls as: how they sound, how long they will listen, what they speak.

Decisions: docs/decisions/convo.testing.callers.personas.md
"""

from dataclasses import dataclass

from deepeval.dataset import Persona
from deepeval.dataset.golden import InterruptionBehavior

# Two peninsular voices no project speaks with. Neither of the fleet's own
# voices is available here and the rule is not aesthetic: a call where both
# sides sound identical is unreadable in the recording, and every voice metric
# that tells the speakers apart by timbre is measuring one person talking to
# themselves. Carolina es_ES is the clinic's and Sara Martín is the shop's —
# `tests/test_personas.py` checks the registry rather than this comment.
ALEX = "7ilYbYb99yBZGMUUKSaf"  # es peninsular male
CAROLINA_RUIZ = "h2cd3gvcqTp3m65Dysk7"  # es peninsular female

SPEAKS_SPANISH = "es"
SPEAKS_BOTH = None  # ElevenLabs detects per line; forcing "es" makes English come out Spanish


@dataclass(frozen=True)
class CallerPersona:
    """Who is on the other end of a synthetic call: a voice, a manner, and a patience."""

    name: str
    voice: str
    style: str
    patience_s: float | None = None
    language: str | None = SPEAKS_SPANISH
    multilingual: bool = False

    @property
    def interrupts(self) -> bool:
        """Does this caller talk over the agent? One number decides it, and it reads better here."""
        return self.patience_s is not None

    def card(self) -> Persona:
        """The same persona in DeepEval's vocabulary, for a simulator or a report."""
        return Persona(
            name=self.name,
            characteristics=self.style,
            voice=self.voice,
            multilingual_stt=self.multilingual,
            interruption_behavior=(
                InterruptionBehavior(frequency="frequent", overlap="insist")
                if self.interrupts
                else None
            ),
        )


APURADO = CallerPersona(
    name="apurado",
    voice=ALEX,
    style=(
        "Llamas con prisa y lo dices. Hablas en frases muy cortas, das los datos de golpe y sin "
        "adornos, y no esperas a que quien te atiende termine: en cuanto entiendes por dónde va "
        "la respuesta, sigues hablando por encima. No eres maleducado, eres alguien que llega "
        "tarde a otra cosa."
    ),
    # Two and a half seconds: long enough for the agent to get its first
    # sentence out (measured answers open in 1.3–1.7 s and the sentence itself
    # runs about two), short enough that a three-sentence reply is cut off
    # mid-way, which is the case worth testing.
    patience_s=2.5,
)

SPANGLISH = CallerPersona(
    name="spanglish",
    voice=CAROLINA_RUIZ,
    style=(
        "Vives entre dos idiomas y cambias del español al inglés a mitad de frase sin darte "
        "cuenta — 'hola, hi, I need to change mi cita del jueves'. No traduces lo que acabas de "
        "decir ni te disculpas por ello; es simplemente cómo hablas. Eres tranquila y dejas "
        "terminar a quien te atiende."
    ),
    language=SPEAKS_BOTH,
    multilingual=True,
)

PERSONAS = {persona.name: persona for persona in (APURADO, SPANGLISH)}


def persona(name: str) -> CallerPersona:
    """The persona a golden names, or a refusal that lists the ones that exist."""
    if name not in PERSONAS:
        known = ", ".join(sorted(PERSONAS))
        raise LookupError(f"no persona {name!r} — ring 2 calls as one of: {known}")
    return PERSONAS[name]

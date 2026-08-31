"""Reagendamiento: move the cita a patient already has, or give them a first one.

ms-3 turns the conversation into a process — Identify, ChooseSlot, Farewell —
and gives it the right to write: `book_slot` is irreversible and unreachable
without a confirmation token, and the three writes that make up a rebooking run
as a saga so a failure halfway leaves the patient's old appointment standing.

ms-20 also closes the two verbs a reception has and this project did not: a cita
could be moved and created, and only ever cancelled as the first half of a move.
`cancel_appointment` is the standalone cancel — the fourth irreversible door,
and the one that gives an hour back instead of taking one, which is why the
freed slot reappears in `find_availability` and why the spec declares no
compensation. `confirm_attendance` is its opposite in every way: the patient
rang to say they ARE coming, nothing is taken from them, and it is a plain
`write` with `rebook_slot` as its undo. Both live in one stage, because the
conversation is one conversation — the cita you already have, and what you want
done with it that is not moving it.

ms-20 adds the third, and it is the first one that is not an appointment:
`update_contact` changes the number the clinic rings the patient on. The verb is
only reachable once the caller has been found on the book — an unidentified
caller cannot change anybody's data — and it goes through the same door as the
other two, which is the point: a new irreversible verb is a ToolSpec, a stage
and a consent graph name, not a new mechanism.

ms-18 adds the second errand and, with it, the second irreversible door.
`Identify` now has two exits and `create_appointment` opens a cita for somebody
the book had never held — through the same guard, the same `ConfirmTask` and a
saga of its own. The project keeps its name: what a caller asks reception for is
an appointment, and whether one already existed is the platform's problem.

The catalog below is the whole of what this project may call. It is data the
platform reads before every call, not documentation: a tool missing from here
cannot run, however convincingly the model asks for it, and the side effect
declared on each spec is what decides whether a caller has to say yes first.

Every spec here also declares a `result_summary` (ms-7): the one line of a
result the session log is allowed to keep, rendered by the adapter that
produced it and masked by the platform before it is written. Reading a
rescheduling call back months later — or scoring it with the grounding metric —
is the difference between "the agent said nine o'clock" and "the agenda offered
nine o'clock and the agent said it".
"""

from dataclasses import dataclass

from core.context import Project, TenantContext
from core.telephony.human import TRANSFER_TO_HUMAN
from core.tools.catalog import ToolCatalog, platform_specs
from core.tools.contract import SideEffect, ToolSpec
from core.tools.messages import FAILURE, NO_ADAPTER, TIMEOUT, UNKNOWN_TOOL

from ...adapters.agenda import (
    summarise_availability,
    summarise_change,
    summarise_contact,
    summarise_patient,
)
from ...adapters.sms import summarise_message
from . import knowledge

# The platform's own `find_availability` spec, re-declared with the one clause only a
# clinic can write: what a free slot may say in the log. The renderer lives next to the
# adapter that produces the rows, so a customer swapping FakeAgenda for their real agenda
# changes the shape and its summary in the same file.
FIND_AVAILABILITY = ToolSpec(
    name="find_availability",
    side_effect=SideEffect.READ,
    timeout_s=5.0,
    result_summary=summarise_availability,
)
FIND_PATIENT = ToolSpec(
    name="find_patient",
    side_effect=SideEffect.READ,
    pii_scope=frozenset({"phone", "name"}),
    timeout_s=5.0,
    result_summary=summarise_patient,
)
CANCEL_SLOT = ToolSpec(
    name="cancel_slot",
    side_effect=SideEffect.WRITE,
    idempotency_key="appointment_id",
    compensation="rebook_slot",
    timeout_s=5.0,
    result_summary=summarise_change,
)
BOOK_SLOT = ToolSpec(
    name="book_slot",
    side_effect=SideEffect.IRREVERSIBLE,
    idempotency_key="slot_id",
    pii_scope=frozenset({"phone", "patient"}),
    compensation="cancel_slot",
    timeout_s=8.0,
    result_summary=summarise_change,
)
# The other irreversible write of this project: a cita for somebody the book did not
# hold. Same shape as BOOK_SLOT and deliberately its own spec — `create_appointment`
# creates the patient's record, so the consent metric watches it by its own name, and a
# reader of the catalog sees two irreversible doors instead of one door with a flag.
CREATE_APPOINTMENT = ToolSpec(
    name="create_appointment",
    side_effect=SideEffect.IRREVERSIBLE,
    idempotency_key="slot_id",
    pii_scope=frozenset({"phone", "patient"}),
    compensation="cancel_slot",
    timeout_s=8.0,
    result_summary=summarise_change,
)
# The third irreversible door, and the one that is not about an hour at all (ms-20).
# Changing the number the clinic reaches a patient on is not compensable by us: nobody
# keeps the number it replaced, and a patient we can no longer ring is a patient who
# misses the appointment we were ringing about. So it declares no compensation — an
# irreversible write with an undo would be a `write` — and the guard demands a token for
# it exactly as it does for the two bookings.
UPDATE_CONTACT = ToolSpec(
    name="update_contact",
    side_effect=SideEffect.IRREVERSIBLE,
    idempotency_key="appointment_id",
    pii_scope=frozenset({"phone"}),
    timeout_s=5.0,
    result_summary=summarise_contact,
)
# The fourth irreversible door, and the one that gives something back instead of taking
# an hour: the patient is not coming. It declares no compensation for a reason the
# adapter spells out — from the moment it runs, `find_availability` offers that half hour
# to the next caller, so "undo" would be a promise about a booking somebody else may
# already hold. `cancel_slot` above is the same field with a different promise: a step
# inside a saga that puts it back in milliseconds. Two promises, two specs, two names.
CANCEL_APPOINTMENT = ToolSpec(
    name="cancel_appointment",
    side_effect=SideEffect.IRREVERSIBLE,
    idempotency_key="appointment_id",
    timeout_s=5.0,
    result_summary=summarise_change,
)
# The one write of this project a caller does not have to agree to twice. Marking a cita
# confirmed takes nothing away from the patient who rang to say they are coming, and
# `rebook_slot` puts the row back to `booked` if it was ever wrong — which is what a
# `write` with a compensation is: reversible, and therefore not a door.
CONFIRM_ATTENDANCE = ToolSpec(
    name="confirm_attendance",
    side_effect=SideEffect.WRITE,
    idempotency_key="appointment_id",
    compensation="rebook_slot",
    timeout_s=5.0,
    result_summary=summarise_change,
)
# The undo of a cancel is a write, never an irreversible: the platform is putting
# things back the way the patient left them, and asking for a second yes to do
# that is not a conversation anybody wants.
REBOOK_SLOT = ToolSpec(
    name="rebook_slot",
    side_effect=SideEffect.WRITE,
    idempotency_key="appointment_id",
    timeout_s=5.0,
    result_summary=summarise_change,
)
# The one verb of this project that is not the clinic's at all: handing the call to a
# person at reception (ms-20). The spec is the platform's — `core.telephony.human` — and
# declaring it here is the opt-in: a project that leaves it out is never offered the tool,
# and so is a project that declares it and names no `transfer_number` below.
SEND_SMS = ToolSpec(
    name="send_sms",
    side_effect=SideEffect.WRITE,
    pii_scope=frozenset({"phone"}),
    timeout_s=5.0,
    result_summary=summarise_message,
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


@dataclass
class ReagendamientoProject(Project):
    """Project with an entry agent factory; voice and keyterms arrive with later milestones."""

    def entry_agent(self, tc: TenantContext):
        """The first stage a caller meets: the one that finds out whose appointment this is."""
        from .stages import Identify

        return Identify(tc)

    def stages(self, tc: TenantContext) -> list:
        """Every stage of the call, in order — the project's whole tool surface for evals."""
        from .stages import (
            CancelOrConfirm,
            ChooseSlot,
            Farewell,
            Identify,
            NewBooking,
            UpdateContact,
        )

        return [
            Identify(tc),
            ChooseSlot(tc),
            NewBooking(tc),
            CancelOrConfirm(tc),
            UpdateContact(tc),
            Farewell(tc),
        ]


PROJECT = ReagendamientoProject(
    id="reagendamiento",
    name="Reagendamiento de citas",
    language="es-ES",
    greeting="Clínica Norte, buenos días, le atiende recepción. ¿En qué puedo ayudarle?",
    voice="UOIqAnmS11Reiei1Ytkc",  # ElevenLabs "Carolina - Spanish woman - es_ES" (used from ms-6)
    tts_model="eleven_flash_v2_5",  # latency profile: ~100ms ttfb vs ~700ms measured on v3 (PSTN)
    # The clinic's own switchboard, the number the SMS already tells patients to ring.
    # Overridable from the console: which phone reception overflows to is a business
    # decision that changes between two calls, not between two deploys.
    transfer_number="+34910000000",
    tools=platform_specs().merge(
        ToolCatalog.of(
            FIND_AVAILABILITY,
            FIND_PATIENT,
            CANCEL_SLOT,
            BOOK_SLOT,
            CREATE_APPOINTMENT,
            UPDATE_CONTACT,
            CANCEL_APPOINTMENT,
            CONFIRM_ATTENDANCE,
            REBOOK_SLOT,
            SEND_SMS,
            TRANSFER_TO_HUMAN,
        )
    ),
    messages=MESSAGES,
    knowledge_seed=knowledge.CLINIC,
)

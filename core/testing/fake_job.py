"""fake_job_context: the shape of a LiveKit job, for router tests that never touch a server.

`core.router.resolve` reads four things off a job — `id`, `metadata`, the
dispatch `attributes` and the SIP `participant.attributes` — and nothing else.
This builds exactly those, as plain objects, so a test can say "a call to this
number on this fleet" in one line.
"""

from dataclasses import dataclass, field


@dataclass
class FakeParticipant:
    """The participant a job was created for; SIP puts the dialled number in its attributes."""

    identity: str = "caller"
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass
class FakeJob:
    """The four fields of a job the router reads."""

    id: str = "AJ_test"
    metadata: str = ""
    attributes: dict[str, str] = field(default_factory=dict)
    participant: FakeParticipant = field(default_factory=FakeParticipant)


@dataclass
class FakeJobContext:
    """Stands where `livekit.agents.JobContext` stands for `resolve`."""

    job: FakeJob = field(default_factory=FakeJob)


def fake_job_context(
    metadata: str = "",
    attributes: dict[str, str] | None = None,
    participant_attributes: dict[str, str] | None = None,
    job_id: str = "AJ_test",
) -> FakeJobContext:
    """A job with the given dispatch metadata and attributes, and SIP participant attributes."""
    return FakeJobContext(
        job=FakeJob(
            id=job_id,
            metadata=metadata,
            attributes=dict(attributes or {}),
            participant=FakeParticipant(attributes=dict(participant_attributes or {})),
        )
    )

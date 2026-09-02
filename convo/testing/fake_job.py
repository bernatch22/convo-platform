"""fake_job_context: the shape of a LiveKit job, for router tests that never touch a server.

Decisions: docs/decisions/convo.testing.fake_job.md
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
class FakeRoom:
    """The room the job runs in; a phone caller is one of its remote participants."""

    remote_participants: dict[str, FakeParticipant] = field(default_factory=dict)


@dataclass
class FakeJobContext:
    """Stands where `livekit.agents.JobContext` stands for `resolve`."""

    job: FakeJob = field(default_factory=FakeJob)
    room: FakeRoom = field(default_factory=FakeRoom)


def fake_job_context(
    metadata: str = "",
    attributes: dict[str, str] | None = None,
    participant_attributes: dict[str, str] | None = None,
    room_participants: dict[str, str] | None = None,
    job_id: str = "AJ_test",
) -> FakeJobContext:
    """A job with the given dispatch metadata and attributes, and a SIP caller either way."""
    return FakeJobContext(
        job=FakeJob(
            id=job_id,
            metadata=metadata,
            attributes=dict(attributes or {}),
            participant=FakeParticipant(attributes=dict(participant_attributes or {})),
        ),
        room=FakeRoom(
            remote_participants=(
                {"caller": FakeParticipant(attributes=dict(room_participants))}
                if room_participants
                else {}
            )
        ),
    )

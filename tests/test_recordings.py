"""Where a call's audio lives, who may hear it, and the one door it is served through.

The recording itself is the framework's — a `RecorderIO` wrapped around the
session's audio IO — so nothing here tries to test Opus. What is ours is the
DESTINATION (which is the whole bug: a real job used to record into a temp dir
the framework then deleted), the opt-out, and a read side that composes a path
from a session id and never from anything a caller sent.
"""

import pytest
from fastapi.testclient import TestClient

import worker
from api import app, open_store
from core import control_plane, recordings
from core.context import Project
from core.state.events import Event
from core.state.store import MemoryStore, SessionRow
from core.testing import fake_context

pytestmark = pytest.mark.unit

HEARD = "sess-heard"
SILENT = "sess-silent"
OGG = b"OggS-not-really-opus-but-bytes-are-bytes"


@pytest.fixture
def root(tmp_path, monkeypatch):
    """A recordings root of this test's own, so nothing reads the laptop's real one."""
    monkeypatch.setenv(recordings.ROOT_ENV, str(tmp_path))
    return tmp_path


@pytest.fixture
def store() -> MemoryStore:
    """Two finished voice calls; only one of them will be given a file."""
    store = MemoryStore()
    for session_id in (HEARD, SILENT):
        store.open_session(
            SessionRow(session_id, "clinica-norte", "reagendamiento", "voice", started_at=1.0)
        )
        store.append(session_id, Event(1, "session.start", 0, {"tenant": "clinica-norte"}))
        store.close_session(session_id, "completed", None)
    return store


@pytest.fixture
def client(store: MemoryStore) -> TestClient:
    app.dependency_overrides[open_store] = lambda: store
    yield TestClient(app)
    app.dependency_overrides.clear()


def written(session_id: str, body: bytes = OGG):
    """Put a recording on disk exactly where a job would have written it."""
    path = recordings.path_for(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return path


# ── where a recording lives ──────────────────────────────────────────────────


def test_a_recording_is_keyed_by_session_id_under_the_configured_root(root) -> None:
    assert recordings.path_for(HEARD) == root / HEARD / "audio.ogg"


def test_a_session_that_wrote_nothing_simply_has_no_recording(root) -> None:
    assert recordings.for_session(HEARD) is None


def test_a_session_that_wrote_one_hands_back_the_file(root) -> None:
    path = written(HEARD)

    assert recordings.for_session(HEARD) == path


def test_an_id_that_could_walk_out_of_the_root_is_refused_before_any_path_exists(root) -> None:
    """The id reaches the read side as a URL segment; no dot ever survives it."""
    for hostile in ("../../etc/passwd", "..", "a/b", "sess id", ""):
        assert recordings.for_session(hostile) is None


# ── who is recorded at all ───────────────────────────────────────────────────


def test_a_project_keeps_its_audio_by_default() -> None:
    assert recordings.keep(Project(id="reagendamiento", name="Reagendamiento")) is True


def test_a_project_can_refuse_to_be_recorded() -> None:
    quiet = Project(id="reagendamiento", name="Reagendamiento", recording=False)

    assert recordings.keep(quiet) is False


# ── aiming a job at its final path ───────────────────────────────────────────


class FakeJob:
    """The one attribute `aim` writes; on a real JobContext it hides behind a property."""

    def __init__(self) -> None:
        self._session_directory = None


class SealedJob:
    """A context that will not take the attribute — the day the framework changes shape."""

    __slots__ = ()


def test_aiming_a_job_points_its_recorder_at_the_final_path(root) -> None:
    ctx = FakeJob()

    path = recordings.aim(ctx, HEARD)

    assert path == root / HEARD / "audio.ogg"
    assert ctx._session_directory == path.parent, "the framework appends audio.ogg to this"
    assert path.parent.is_dir(), "the directory exists before the first flush needs it"


def test_aiming_fails_closed_so_a_changed_framework_stops_recording_not_the_fleet(root) -> None:
    assert recordings.aim(SealedJob(), HEARD) is None


# ── the bolt on the door ─────────────────────────────────────────────────────


def test_with_no_token_configured_the_route_is_as_open_as_every_other_read(monkeypatch) -> None:
    monkeypatch.delenv(recordings.TOKEN_ENV, raising=False)

    assert recordings.authorised(None) is True


def test_a_configured_token_admits_only_itself(monkeypatch) -> None:
    monkeypatch.setenv(recordings.TOKEN_ENV, "s3cret")

    assert recordings.authorised("s3cret") is True
    assert recordings.authorised("something-else") is False
    assert recordings.authorised(None) is False


# ── the route ────────────────────────────────────────────────────────────────


def test_the_route_serves_the_ogg_of_a_call_that_left_one(root, client) -> None:
    written(HEARD)

    response = client.get(f"/sessions/{HEARD}/recording")

    assert response.status_code == 200
    assert response.content == OGG
    assert response.headers["content-type"] == "audio/ogg"
    assert HEARD in response.headers["content-disposition"]


def test_the_route_refuses_a_session_this_deploy_never_heard_of(root, client) -> None:
    written("sess-not-in-the-store")

    response = client.get("/sessions/sess-not-in-the-store/recording")

    assert response.status_code == 404, "a file on disk is not a session"


def test_a_session_with_no_audio_is_a_404_and_not_an_empty_body(root, client) -> None:
    assert client.get(f"/sessions/{SILENT}/recording").status_code == 404


def test_a_hostile_id_never_comes_back_as_a_recording(root, client) -> None:
    """`%2F` is decoded before routing, so who answers depends on whether `ui/dist`
    is built: this route (404) or the SPA fallback (index.html). The invariant is
    neither of those — it is that no audio ever comes back from an id like this."""
    response = client.get("/sessions/..%2F..%2Fetc%2Fpasswd/recording")

    assert response.headers.get("content-type") != recordings.MEDIA_TYPE


def test_the_token_bolts_the_route_and_both_ways_of_presenting_it_open_it(
    root, client, monkeypatch
) -> None:
    written(HEARD)
    monkeypatch.setenv(recordings.TOKEN_ENV, "s3cret")

    assert client.get(f"/sessions/{HEARD}/recording").status_code == 401
    header = {"Authorization": "Bearer s3cret"}
    assert client.get(f"/sessions/{HEARD}/recording", headers=header).status_code == 200
    assert client.get(f"/sessions/{HEARD}/recording?t=s3cret").status_code == 200


# ── what the console reads to decide whether to draw a player ────────────────


def test_the_session_line_says_which_calls_can_be_played(root, store) -> None:
    written(HEARD)

    lines = {row["id"]: row["audio"] for row in control_plane.sessions(store)}

    assert lines == {HEARD: True, SILENT: False}


# ── which calls the worker even arms the recorder for ────────────────────────


def voice_job(monkeypatch, **project_fields):
    """A resolved context and a job, as `worker.entrypoint` has them in hand."""
    monkeypatch.delenv("RECORD", raising=False)
    tc = fake_context("clinica-norte", "reagendamiento", channel="voice")
    for name, value in project_fields.items():
        setattr(tc.project, name, value)
    return FakeJob(), tc


def test_an_ordinary_voice_job_records_into_the_recordings_root(root, monkeypatch) -> None:
    """The whole point of ms-17: no flag, no console, and the call still keeps its audio."""
    ctx, tc = voice_job(monkeypatch)

    assert worker.audio_destination(ctx, tc) == root / tc.session_id / "audio.ogg"


def test_a_project_that_refused_recording_arms_nothing(root, monkeypatch) -> None:
    ctx, tc = voice_job(monkeypatch, recording=False)

    assert worker.audio_destination(ctx, tc) is None
    assert ctx._session_directory is None, "a refused project is never even aimed"


def test_a_chat_session_has_no_audio_to_keep(root, monkeypatch) -> None:
    ctx, tc = voice_job(monkeypatch)
    tc.channel = "chat"

    assert worker.audio_destination(ctx, tc) is None


def test_a_whole_deploy_can_switch_recording_off(root, monkeypatch) -> None:
    ctx, tc = voice_job(monkeypatch)
    monkeypatch.setenv("RECORD", "0")

    assert worker.audio_destination(ctx, tc) is None

"""A supervisor's ticket: what the signed token lets them do, and who the agent will believe.

Every assertion here reads the JWT the way the SFU will read it — decoded with
the secret this deploy signs with — because a grant that is only in the Python
call is a grant that does not exist. The identity gate is pinned in the same
file on purpose: the token is what mints `sup:`, and `is_supervisor` is the
only thing downstream that looks at it.
"""

import os

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

from api import app
from core.auth import SUPERVISOR_TTL, mint_supervisor
from core.security.supervisor import KINDS, is_supervisor

pytestmark = pytest.mark.unit

ROOM = "clinica-norte-reagendamiento-ab12cd34"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_a_listen_ticket_hears_the_room_and_can_publish_nothing() -> None:
    grants = _decoded(mint_supervisor(ROOM, "listen")["token"])["video"]

    assert grants["room"] == ROOM and grants["roomJoin"] is True
    assert grants["canSubscribe"] is True
    assert not grants.get("canPublish"), "listening is not a microphone, whatever the browser does"
    assert not grants.get("canPublishData")
    assert grants["hidden"] is True, "the caller is never told somebody joined to listen"


def test_a_whisper_ticket_stays_hidden_and_silent_but_may_send_data() -> None:
    grants = _decoded(mint_supervisor(ROOM, "whisper")["token"])["video"]

    assert grants["canPublishData"] is True, "a whisper travels on the data channel"
    assert not grants.get("canPublish") and grants["hidden"] is True


def test_a_takeover_ticket_publishes_audio_and_appears_in_the_room() -> None:
    grants = _decoded(mint_supervisor(ROOM, "takeover")["token"])["video"]

    assert grants["canPublish"] is True and grants["canPublishData"] is True
    assert not grants.get("hidden"), "a human on the line is a participant, not a ghost"


def test_the_grant_names_exactly_one_room() -> None:
    grants = _decoded(mint_supervisor(ROOM, "takeover")["token"])["video"]

    assert grants["room"] == ROOM
    assert not grants.get("roomAdmin") and not grants.get("roomList")


def test_the_identity_is_the_supervisor_prefix_and_the_role_attribute_is_signed() -> None:
    ticket = mint_supervisor(ROOM, "listen", user_id="berna")
    claims = _decoded(ticket["token"])

    assert ticket["identity"] == "sup:berna" and claims["sub"] == "sup:berna"
    assert claims["attributes"] == {"role": "supervisor", "cap": "listen"}
    assert ticket["capability"] == "listen"


def test_one_human_keeps_one_identity_when_they_take_the_line() -> None:
    listening = mint_supervisor(ROOM, "listen", user_id="berna")
    taking = mint_supervisor(ROOM, "takeover", user_id="berna")

    assert listening["identity"] == taking["identity"], "an upgrade, not a second ghost"


def test_a_supervisor_who_did_not_say_who_they_are_still_gets_a_scoped_identity() -> None:
    identity = mint_supervisor(ROOM, "listen")["identity"]

    assert identity.startswith("sup:") and len(identity) > len("sup:")


def test_a_supervisor_ticket_is_short_lived() -> None:
    claims = _decoded(mint_supervisor(ROOM, "listen")["token"])

    assert claims["exp"] - claims["nbf"] == pytest.approx(SUPERVISOR_TTL.total_seconds(), abs=2)


def test_a_supervisor_ticket_carries_no_agent_dispatch() -> None:
    claims = _decoded(mint_supervisor(ROOM, "takeover")["token"])

    assert "roomConfig" not in claims, "a supervisor joins a call; it never starts one"


def test_an_unknown_capability_is_refused_and_names_the_known_ones() -> None:
    with pytest.raises(ValueError, match="admin"):
        mint_supervisor(ROOM, "admin")  # type: ignore[arg-type]


def test_only_a_sup_identity_is_a_supervisor() -> None:
    assert is_supervisor("sup:x") is True

    assert is_supervisor("cc") is False
    assert is_supervisor("observer:x") is False
    assert is_supervisor("") is False, "an unnamed participant fails closed"
    assert is_supervisor("clinica-norte:u1") is False
    assert is_supervisor("agent-cc") is False


def test_the_audit_vocabulary_is_five_dotted_supervisor_kinds() -> None:
    assert KINDS == (
        "supervisor.join",
        "supervisor.steer",
        "supervisor.takeover",
        "supervisor.release",
        "supervisor.transfer",
    )


def test_the_endpoint_defaults_to_listening_and_refuses_an_unknown_capability(client) -> None:
    ticket = client.post("/supervise", json={"room": ROOM}).json()

    assert ticket["capability"] == "listen" and ticket["identity"].startswith("sup:")
    assert _decoded(ticket["token"])["video"]["hidden"] is True
    assert client.post("/supervise", json={"room": ROOM, "capability": "admin"}).status_code == 422
    assert client.post("/supervise", json={}).status_code == 422
    assert client.post("/supervise", json={"room": ROOM, "hidden": False}).status_code == 422


def _decoded(token: str) -> dict:
    """Read a minted token with the secret this deploy actually signed it with."""
    secret = os.getenv("LIVEKIT_API_SECRET", "secret")
    return pyjwt.decode(token, secret, algorithms=["HS256"], options={"verify_aud": False})

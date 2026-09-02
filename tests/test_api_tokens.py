"""The control plane's token: minted at the door, readable by the router, refused for strangers."""

import json
import os

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

from convo.api.app import app
from convo.domain.contracts import SessionMeta
from convo.session.router import session_meta
from convo.testing.fake_job import fake_job_context

pytestmark = pytest.mark.unit

client = TestClient(app)


def decoded(token: str) -> dict:
    """Read a minted token with the secret the door actually signed it with.

    Not the literal `"secret"`: since ms-10 a laptop's `.env` carries the real
    box keypair, and a test that hardcodes the dev default goes red the day
    the platform gets a server.
    """
    secret = os.getenv("LIVEKIT_API_SECRET", "secret")
    return pyjwt.decode(token, secret, algorithms=["HS256"], options={"verify_aud": False})


def test_a_token_names_the_room_the_caller_and_the_dispatch() -> None:
    body = {"tenant": "tienda-sur", "project": "pedidos", "channel": "chat", "user_id": "u1"}
    reply = client.post("/token", json=body).json()

    claims = decoded(reply["token"])
    assert claims["video"]["room"] == reply["room"], "the grant is an exact room, never a wildcard"
    assert reply["room"].startswith("tienda-sur-pedidos-")
    agent = claims["roomConfig"]["agents"][0]
    assert agent["agentName"] == os.getenv("FLEET", "cc"), "never empty: empty = implicit dispatch"
    assert json.loads(agent["metadata"])["tenant"] == "tienda-sur"


def test_the_dispatch_metadata_round_trips_through_the_router() -> None:
    body = {"tenant": "clinica-norte", "project": "reagendamiento", "channel": "voice"}
    reply = client.post("/token", json=body).json()

    payload = decoded(reply["token"])["roomConfig"]["agents"][0]["metadata"]
    ctx = fake_job_context(metadata=payload)
    meta = session_meta(ctx, store=None)

    assert meta == SessionMeta(tenant="clinica-norte", project="reagendamiento", channel="voice")


def test_an_unknown_tenant_or_project_is_refused_with_the_known_list() -> None:
    body = {"tenant": "acme", "project": "x"}
    reply = client.post("/token", json=body)
    assert reply.status_code == 404 and "clinica-norte" in reply.json()["detail"]

    body = {"tenant": "clinica-norte", "project": "x"}
    reply = client.post("/token", json=body)
    assert reply.status_code == 404 and "reagendamiento" in reply.json()["detail"]


def test_tenants_lists_what_this_deploy_serves() -> None:
    reply = client.get("/tenants").json()
    by_id = {row["tenant"]: row for row in reply}
    assert {"clinica-norte", "tienda-sur"} <= set(by_id)
    voices = {p["id"]: p["voice"] for p in by_id["clinica-norte"]["projects"]}
    assert voices["reagendamiento"], "voice is project data, and the client needs it"


def test_the_unit_ring_cannot_reach_a_provider() -> None:
    from tests.conftest import OFFLINE_KEY

    assert os.environ.get("ANTHROPIC_API_KEY") == OFFLINE_KEY, "the LLM key is a dead sentinel"
    for key in ("SONIOX_API_KEY", "ELEVENLABS_API_KEY"):
        assert key not in os.environ, f"{key} must be stripped inside the unit ring"

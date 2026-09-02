"""A second human on a live call: observe, enter, and the supervision verbs."""

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from convo.api.auth import (
    SupervisorCapability,
    mint_observer,
    mint_supervisor,
)
from convo.session.rooms import RoomsUnreachable
from convo.supervision import desk

router = APIRouter()


class ObserveRequest(BaseModel):
    """The one thing a supervisor must name to listen in: the room, exactly."""

    model_config = ConfigDict(extra="forbid")

    room: str


class SuperviseRequest(BaseModel):
    """A supervisor asking to be let into one live room, with one set of powers."""

    model_config = ConfigDict(extra="forbid")

    room: str
    capability: SupervisorCapability = "listen"
    user_id: str = ""


class EnteredRequest(BaseModel):
    """A supervisor saying they are through the door; the SFU is asked whether it is true.

    Nothing here is trusted beyond "look at this room for this identity". The
    capability is read off the participant's signed attributes at the SFU, not
    taken from this body — which is why there is no field for it.
    """

    model_config = ConfigDict(extra="forbid")

    room: str
    identity: str


class VerbRequest(BaseModel):
    """One supervision verb, aimed at a live room from the control plane rather than a browser.

    `identity` is the supervisor the SFU will be asked about; nothing here is
    trusted beyond "look at this room for this identity". The agent asks the
    same question again of the packet it receives.

    `mode` is per-verb and deliberately one field: `inject` / `inject_and_speak`
    for a steer, `cold` / `warm` for a transfer. Empty means "this verb's
    default", which is the only value that is right for every verb.
    """

    model_config = ConfigDict(extra="forbid")

    room: str
    identity: str
    verb: Literal["steer", "takeover", "release", "transfer"]
    text: str = ""
    mode: Literal["", "inject", "inject_and_speak", "cold", "warm"] = ""
    deaf: bool = False
    to: str = ""


@router.post("/observe")
def observe(req: ObserveRequest) -> dict[str, str]:
    """Mint a listen-only ticket into one live room, for a supervisor watching a call.

    → `{"url": str, "room": str, "identity": "observer:<hex>", "token": "<jwt>"}`

    The grant is `room_join` on that exact room with `can_publish=False`,
    `can_publish_data=False` and `hidden=True`: the browser receives audio and
    the agent's `lk.transcription` stream, publishes nothing, and never
    appears in the room — the caller is not told anybody joined.
    """
    return mint_observer(req.room)


@router.post("/supervise")
def supervise(req: SuperviseRequest) -> dict[str, str]:
    """Mint a role-scoped, short-lived ticket for a supervisor entering one live call.

    → `{"url": str, "room": str, "identity": "sup:<uid>", "capability": str,
         "token": "<jwt>"}`

    `capability` is the whole of the difference: `listen` is hidden and
    subscribe-only, `whisper` may also send data, `takeover` publishes audio
    and appears in the room. The ticket expires in
    `core.auth.SUPERVISOR_TTL`, so it is a ticket to this call and not a
    standing key to the room.

    This is where a deployment's own auth goes: the handler is deliberately
    thin, and the human on the other side of it is authenticated by whatever
    the control plane already authenticates humans with. Everything downstream
    — the SFU and the agent both — trusts only the signed `sup:` identity in
    the JWT this returns, never a role a client claims in a payload.
    """
    return mint_supervisor(req.room, req.capability, user_id=req.user_id)


@router.post("/supervise/entered")
async def supervise_entered(req: EnteredRequest) -> dict[str, Any]:
    """Record that a supervisor really did enter this call, and say what the SFU sees.

    → `{"identity": "sup:<uid>", "capability": str, "hidden": bool, "announced": bool}`

    Two things happen and both matter. The SFU is asked who is in the room, so
    the answer is a *presence* and not a ticket somebody was handed — `hidden`
    is the server's own word for "the caller cannot see this participant", which
    is what the desk shows the supervisor. And the arrival is announced to the
    room's agent alone, on the `supervisor` data topic, which is what puts
    `supervisor.join` in the caller's log with the next `seq`: the job process
    owns that log, so the fact has to reach it rather than be written around it.

    `announced` is False when no agent is in the room — nothing is being logged
    there either. → 404 when the identity is not in the room, 503 when the SFU
    cannot be asked.
    """
    try:
        return await desk.entered(req.room, req.identity)
    except desk.NotInRoom as error:
        raise HTTPException(404, str(error)) from error
    except RoomsUnreachable as error:
        raise HTTPException(503, str(error)) from error


@router.post("/supervise/verb")
async def supervise_verb(req: VerbRequest) -> dict[str, Any]:
    """Whisper to a live agent, take its line, hand it back, or move the call — server-side.

    → `{"verb": str, "identity": "sup:<uid>", "sent": true}`

    The browser desk does not come through here: it holds a `whisper` ticket
    and calls the agent's own `supervisor.steer` RPC, which is one hop instead
    of three. This exists for the callers that have no room connection — an
    escalation rule, a compliance trigger, a `curl` in a terminal — and for
    the demo that shows a whisper landing without a browser at all:

        curl -XPOST localhost:8000/supervise/verb -H 'content-type: application/json' \
          -d '{"room":"...","identity":"sup:berna","verb":"steer","text":"ve al grano"}'

    A transfer is the same door with a destination on it — `mode` is `cold`
    (a SIP REFER: the caller leaves for that number and the call ends here) or
    `warm` (the colleague is dialled INTO the room, briefed where the caller
    cannot hear it, then bridged), and `to` is E.164, defaulting to the
    deployment's `TRANSFER_TO`:

        curl -XPOST localhost:8000/supervise/verb -H 'content-type: application/json' \
          -d '{"room":"...","identity":"sup:berna","verb":"transfer","mode":"cold",
               "to":"+34600111222"}'

    What happens next is the agent's decision, not this handler's: the packet
    reaches the job that owns the caller's log, `SupervisorControl` checks the
    identity again, applies the verb at a turn boundary and writes the line
    with the next `seq`. → 404 when the supervisor or the agent is not in the
    room, 422 for a verb this door does not forward, 503 when the SFU cannot
    be asked.
    """
    body = {"text": req.text, "mode": req.mode, "deaf": req.deaf, "to": req.to}
    try:
        return await desk.command(req.room, req.identity, req.verb, body)
    except desk.NotInRoom as error:
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except RoomsUnreachable as error:
        raise HTTPException(503, str(error)) from error

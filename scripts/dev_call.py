"""dev_call.py — a browser-less chat call against the local LiveKit server.

The stack runs in three terminals (compose up · `uvicorn api:app` ·
`python worker.py dev`); this script is the fourth, standing in for the web
client nobody has written yet. It asks the control plane for a token, joins the
room that token names, types on `lk.chat`, reads the agent's deltas on
`lk.transcription` and hangs up.

    uv run python scripts/dev_call.py                          # both demo tenants
    uv run python scripts/dev_call.py clinica-norte/reagendamiento
    uv run python scripts/dev_call.py tienda-sur/pedidos "hola" "¿cuándo llega?"

Nothing below knows a tenant. Who answers is decided by the dispatch metadata
inside the token — `RoomAgentDispatch(agent_name=FLEET, metadata=SessionMeta)`
— which is exactly what this run exists to prove: one worker process, two
businesses, no `TENANT` in its environment.

Open source note: this is a generic LiveKit text-mode client in 150 lines. Point
`--api` at any control plane that mints `{url, room, token}` and it works.
"""

import asyncio
import json
import sys
from dataclasses import dataclass, field
from urllib.request import Request, urlopen

from livekit import rtc

CHAT_TOPIC = "lk.chat"
TRANSCRIPTION_TOPIC = "lk.transcription"
DEFAULT_API = "http://localhost:8090"
REPLY_TIMEOUT_S = 90.0
QUIET_AFTER_REPLY_S = 4.0

DEMO_CALLS: dict[str, list[str]] = {
    "clinica-norte/reagendamiento": [
        "Hola, llamo desde el 600123456 y quiero cambiar mi cita.",
        "¿Qué huecos tienen esa semana por la mañana?",
    ],
    "tienda-sur/pedidos": [
        "Buenas, llamo por el pedido TS-10432.",
        "¿Cuándo llega y con qué transportista?",
    ],
}


def main(argv: list[str]) -> int:
    """Run the demo calls, or the one `<tenant>/<project> [turn ...]` named on the command line."""
    api, rest = _api_flag(argv)
    calls = {rest[0]: list(rest[1:]) or DEMO_CALLS.get(rest[0], [])} if rest else DEMO_CALLS
    for reference, turns in calls.items():
        if not turns:
            print(f"no turns for {reference}: pass them as arguments")
            return 2
        tenant, _, project = reference.partition("/")
        asyncio.run(chat(api, tenant, project, turns))
    return 0


async def chat(api: str, tenant: str, project: str, turns: list[str]) -> None:
    """One whole call: token, join, greeting, every turn answered, hang up."""
    ticket = mint(api, tenant, project)
    call = ChatCall(identity=f"{tenant}:dev_call")
    print(f"\n── {tenant}/{project} · room {ticket['room']} ──")
    await call.join(ticket)
    try:
        print(f"agent  ▸ {await call.reply()}")
        for line in turns:
            print(f"you    ▸ {line}")
            await call.say(line)
            print(f"agent  ▸ {await call.reply()}")
    finally:
        await call.hang_up()
    print(f"── hung up · {tenant}/{project} ──")


def mint(api: str, tenant: str, project: str) -> dict[str, str]:
    """Ask the control plane for `{url, room, token}` for a chat session with this project."""
    body = json.dumps({"tenant": tenant, "project": project, "channel": "chat"}).encode()
    request = Request(f"{api}/token", data=body, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=10) as reply:
        return json.load(reply)


@dataclass
class ChatCall:
    """A text participant in one room: it types, it reads, it leaves."""

    identity: str
    room: rtc.Room = field(default_factory=rtc.Room)
    inbox: asyncio.Queue[str] = field(default_factory=asyncio.Queue)
    readers: set[asyncio.Task] = field(default_factory=set)

    async def join(self, ticket: dict[str, str]) -> None:
        """Connect to the room and start listening to whoever is not us."""
        self.room.register_text_stream_handler(TRANSCRIPTION_TOPIC, self._on_text)
        await self.room.connect(ticket["url"], ticket["token"])

    async def say(self, text: str) -> None:
        """Send one user turn on `lk.chat`, the topic the framework's room IO listens on."""
        await self.room.local_participant.send_text(text, topic=CHAT_TOPIC)

    async def reply(self) -> str:
        """The agent's whole answer: the first segment, plus any that follow it right away.

        A turn that calls a tool speaks twice — "un momento, le consulto" and
        then the answer — so waiting for one segment and moving on would type
        the next line over the agent's mouth.
        """
        segments = [await asyncio.wait_for(self.inbox.get(), REPLY_TIMEOUT_S)]
        while True:
            try:
                segments.append(await asyncio.wait_for(self.inbox.get(), QUIET_AFTER_REPLY_S))
            except TimeoutError:
                return " ".join(segments)

    async def hang_up(self) -> None:
        """Leave the room; the session closes with us (RoomOptions.close_on_disconnect)."""
        await self.room.disconnect()

    def _on_text(self, reader: rtc.TextStreamReader, participant_identity: str) -> None:
        """Queue one finished segment — ours come back on this topic too, and are dropped."""
        if participant_identity == self.identity:
            return
        task = asyncio.create_task(self._drain(reader))
        self.readers.add(task)  # a task nobody holds is a task the GC may cancel
        task.add_done_callback(self.readers.discard)

    async def _drain(self, reader: rtc.TextStreamReader) -> None:
        await self.inbox.put((await reader.read_all()).strip())


def _api_flag(argv: list[str]) -> tuple[str, list[str]]:
    """Pull `--api <url>` out of the arguments; everything else is the call to make."""
    if argv[:1] == ["--api"]:
        return argv[1], argv[2:]
    return DEFAULT_API, argv


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

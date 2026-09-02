"""dev_call.py — a browser-less chat call against the local LiveKit server.

Decisions: docs/decisions/infra.scripts.dev_call.md
"""

import argparse
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
    parser = argparse.ArgumentParser(prog="dev_call.py", description=__doc__.split("\n")[0])
    parser.add_argument("--api", default=DEFAULT_API, help="the control plane that mints tokens")
    parser.add_argument("call", nargs="?", help="<tenant>/<project>; omitted, both demo tenants")
    parser.add_argument("turns", nargs="*", help="what to say, one argument per turn")
    args = parser.parse_args(argv)
    api, rest = args.api, ([args.call, *args.turns] if args.call else [])
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
        """The agent's whole answer: the first segment, plus any that follow it right away."""
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


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

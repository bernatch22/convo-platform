"""Record one scripted call with the agent SPEAKING, and no microphone anywhere.

    uv run python -m core.testing.record clinica-norte reagendamiento

The caller's lines are typed (the list below); the agent's are synthesised by
the project's real ElevenLabs voice and played, in real time, into the stereo
OGG the framework writes for a `--record` call. What comes out is a session in
`tmp/convo.db` and an `audio.ogg` next to it — exactly the two things
`python -m convo sessions show|eval <id> --voice` reads.

Why not a real console call: Soniox bills per second of audio and the
offline voice metrics never look at the caller's channel, so sending it
anything would be paying for silence. The key is dropped from the environment
here so the session cannot open a Soniox stream by accident, which also means
**no `stt.final` events in this log**. The trade is written down in
`docs/evals.md` §3.9; `python worker.py console --record` is the run that has
them, and it needs a human with a microphone.
"""

import asyncio
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

RECORDINGS = Path("tmp/recordings")

# One rescheduling call: identify, ask what is free, take the first hour, say yes.
# The spare "sí, confirmo" is for the turn Haiku sometimes spends asking again.
CALL = [
    "Buenos días, llamo para cambiar mi cita. Soy Ana García Ruiz, teléfono 600 12 34 56.",
    "¿Qué huecos hay el jueves?",
    "La primera que me ha dicho.",
    "Sí, confirmo.",
    "Sí, confirmo.",
]


async def record(tenant_id: str, project_id: str, lines: list[str]) -> tuple[str, Path]:
    """Run the script with audio on and return the session id and the OGG it wrote."""
    # imported after the environment is settled: the providers read it at build time
    from core.state.attach import attach_log, close_log
    from core.state.store import SQLiteStore
    from core.testing.harness import fake_context, live_conversation

    tc = fake_context(tenant_id, project_id, channel="voice")
    tc.session_id = f"rec-{uuid.uuid4().hex[:8]}"
    path = RECORDINGS / tc.session_id / "audio.ogg"
    attach_log(tc, SQLiteStore())
    async with live_conversation(tc, record=path) as call:
        for line in lines:
            await call.say(line)
            print(f"> {line}\n< {call.conversation.reply(-1)}\n")
    close_log(tc)
    return tc.session_id, path


def main(argv: list[str]) -> int:
    """CLI: tenant and project ids; prints the session id to read the log back with."""
    load_dotenv(".env")
    if not os.getenv("ELEVENLABS_API_KEY"):
        print("ELEVENLABS_API_KEY is not set: there is nothing to record.")
        return 2
    os.environ.pop("SONIOX_API_KEY", None)  # no microphone, so nothing to transcribe
    tenant_id = argv[1] if len(argv) > 1 else "clinica-norte"
    project_id = argv[2] if len(argv) > 2 else "reagendamiento"
    session_id, path = asyncio.run(record(tenant_id, project_id, CALL))
    print(f"session {session_id}\naudio   {path}")
    print(f"\npython -m convo sessions show {session_id}")
    print(f"python -m convo sessions eval {session_id} --voice")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

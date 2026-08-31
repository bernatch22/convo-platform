# convo-box — the phone path

How a call from a mobile reaches a worker running on a laptop, and how to
rebuild every piece of it. The box itself (SFU, SIP, Redis) is `setup.sh`;
this file is the telephone that plugs into it.

## The path

```
  ☎  mobile
  │  PSTN
  ▼
  Twilio Elastic SIP Trunk "convo-platform"   TK150b9c…
  │   the number +14176743169 is ATTACHED to the trunk, so its
  │   voice_url/webhook is ignored: the trunk owns the call
  │   Origination URI  sip:lk.bernardocastro.dev;transport=udp
  ▼  INVITE, UDP 5060, from Twilio's signalling CIDRs
  convo-box  34.58.189.131   (lk.bernardocastro.dev)
  ├─ livekit-sip v1.12   sip_port 5060, rtp 10000-20000/udp
  │    hide_inbound_port: true  →  an INVITE is only accepted because a
  │    SIPInboundTrunk DECLARES that number. No trunk, no call — silently.
  │    SIPInboundTrunk  ST_iZ4fnskCB7jp   numbers=[+14176743169]
  │                                       allowed_addresses = Twilio's CIDRs
  │    SIPDispatchRule  SDR_mTAegjvJjMbH  individual room "call-…",
  │                                       roomConfig.agents = [ agent_name "cc" ]
  ▼  the SIP participant joins with sip.trunkPhoneNumber, sip.callID, …
  livekit-server 1.9.1   creates the room, dispatches the fleet
  ▼  ws://lk.bernardocastro.dev:7880   (the worker dialled OUT to here)
  laptop   python worker.py dev
       core/sip.py     reads the caller's sip.* attributes off the ROOM
       core/router.py  store.route("cc", "+14176743169")  →  clinica-norte /
                       reagendamiento / voice     ← the ONLY tenant decision
```

The dispatch rule names **no tenant**. A phone number is a route, never a
project: moving that number to another business is one row in the `routes`
table and no LiveKit change at all.

## Rebuild it

```bash
uv run python scripts/twilio_trunk.py --number +14176743169 --dry-run \
    --twilio-env ~/pinecall/sdk-server/.env.production      # read, create nothing
uv run python scripts/twilio_trunk.py --number +14176743169 \
    --twilio-env ~/pinecall/sdk-server/.env.production      # create what is missing
uv run python -m convo routes add cc +14176743169 clinica-norte reagendamiento voice
uv run python -m convo routes list
env -u TENANT -u PROJECT uv run python worker.py dev        # then call the number
```

The script is idempotent: it reads first and creates only what is missing, so
a second run prints the same ids and changes nothing.

Credentials: `TWILIO_ACCOUNT_SID` plus **either** `TWILIO_AUTH_TOKEN` **or**
`TWILIO_API_KEY`/`TWILIO_API_SECRET`, and the box's
`LIVEKIT_URL`/`LIVEKIT_API_KEY`/`LIVEKIT_API_SECRET` (written into `.env` by
`setup.sh`). `--twilio-env` reads a dotenv file; the project's own `.env` wins
over it. Nothing is ever printed but resource ids.

The account is pinecall's (`AC…6442`). Its `TWILIO_API_KEY` in
`~/pinecall/sdk-server/.env.production` **is revoked** — every REST call with it
answers `401 code 20003`, as do all four profiles in `~/.twilio-cli/config.json`.
The credential that works today is the `TWILIO_ACCOUNT_SID` +
`TWILIO_AUTH_TOKEN` pair in `~/pinecall/playground/.env`; `pinecall env pull`
is what re-syncs the production file once the key is rotated.

## The same four things in the Twilio console

| Console | API |
|---|---|
| Elastic SIP Trunking → Trunks → **Create new SIP Trunk**, name `convo-platform` | `POST /v1/Trunks` |
| that trunk → **Origination** → Add Origination URI `sip:lk.bernardocastro.dev;transport=udp`, priority 10, weight 10, enabled | `POST /v1/Trunks/{sid}/OriginationUrls` |
| that trunk → **Numbers** → Add an existing number → `+14176743169` | `POST /v1/Trunks/{sid}/PhoneNumbers` |
| Phone Numbers → the number → its **Voice Configuration is now greyed out** | the trunk owns the call |

Termination (our side dialling out through Twilio) needs a `domain_name` on
the trunk and credentials; this card is inbound only, so neither exists yet.

## Verifying without a phone

Every layer can be checked from the laptop, and only the last one needs a human:

```bash
# 1. the trunk, the URI and the attachment, from Twilio itself
uv run python scripts/twilio_trunk.py --number +14176743169 --dry-run --twilio-env …
# 2. livekit-sip is up and armed
ssh convo-box 'sudo docker ps; sudo docker logs --tail 50 convo-sip-1'
# 3. the route row exists on the db the worker reads
uv run python -m convo routes list
# 4. the worker registered with the SFU
env -u TENANT -u PROJECT uv run python worker.py dev   # "registered worker … agent_name=cc"
# 5. the whole path, minus the audio — see below
uv run python scripts/sip_probe.py
uv run python -m convo sessions list
# 6. only now, and only for the audio: dial the number from a mobile
```

`scripts/sip_probe.py` sends the INVITE Twilio would send. A `200 OK` proves
the trunk admitted the number, the rule opened a `call-…` room and `cc` was
dispatched; the session log then shows which tenant `store.route` resolved and
what the agent said. It sends no RTP, so the audio is the one thing left for
the phone. **It only works if you add your own address to the trunk's
`allowed_addresses` for the run** — from anywhere else the INVITE is dropped,
which is the point of the allow-list.

Run twice on 2026-08-31, before and after the trunk was recreated: `200 OK`, room
`call-_+34600111222_…`, `session.start` carrying `sip.trunkPhoneNumber
+14176743169` / `sip.trunkID` / `sip.ruleID`, tenant `clinica-norte /
reagendamiento`, and the agent opening with *"Clínica Norte, buenos días, le
atiende recepción."* — €0.008 per probe.

## Gotchas paid for once

- **`hide_inbound_port: true` fails silently.** An INVITE for a number no
  `SIPInboundTrunk` declares is dropped with no SIP response at all — the
  caller hears silence and the box logs nothing interesting. The trunk's
  `numbers` field is the allow-list, not documentation.
- **A phone call is a room job, not a participant job.** The dispatch rule
  asks for the agent when the room is created, so `ctx.job.participant` is
  empty and `sip.trunkPhoneNumber` is on a participant *in the room*. Reading
  it off the job routes every call to the default tenant instead
  (`core/sip.py` exists for exactly this).
- **`TENANT` in the environment beats the phone.** Run the worker with
  `env -u TENANT -u PROJECT` or the console's tenant answers the call.
- **Twilio will not let you test it with a call of your own.** Dialling the
  trunk's number from another number on the *same* Twilio account is refused
  with `21216 Account not allowed to call` (loop prevention), so there is no
  self-test over the PSTN — hence `sip_probe.py`.
- **`krisp_enabled` is a LiveKit Cloud feature.** It was left off the trunk
  rather than shipped untested into a self-hosted media path, and it cannot be
  turned off with `update_inbound_trunk_fields`: the trunk has to be deleted
  and recreated, which changes its id and orphans the dispatch rule.
- **The routes table is a file.** `CONVO_DB` (default `tmp/convo.db`) is
  relative to the working directory: add the route and run the worker from
  the same directory, or the number has no route.

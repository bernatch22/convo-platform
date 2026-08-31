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

## Call transfer — the toggles that decide whether a REFER is carried

A **cold transfer** is `livekit-sip` sending a SIP REFER on the caller's own
leg. Whether that REFER is honoured is entirely the carrier's decision, and on
an Elastic SIP Trunk it is two properties on the Trunk resource. Neither is set
by anything in this repo — `scripts/twilio_trunk.py` **reads and reports** them
and prints the command below, because switching them on costs money on every
transfer and a script that mutates a trunk's call settings is exactly the shape
of the 2026 fraud incident.

| what | property | values | default |
|---|---|---|---|
| carry a REFER at all, and to the PSTN | `transfer_mode` | `disable-all` · `sip-only` · `enable-all` | undocumented; every doc example shows `disable-all` |
| whose number the transferee sees | `transfer_caller_id` | `from-transferee` · `from-transferor` | `from-transferee` (documented) |

`sip-only` is not enough for us: the destination is a mobile, so it must be
`enable-all`. (Twilio never writes down which enum value corresponds to the
console's PSTN checkbox — this is the only reading consistent with both, and
it is the value LiveKit's own docs tell you to set.)

```bash
# read — this is what the script prints for you on every run
twilio api trunking v1 trunks fetch --sid TKxxxxxxxx
curl -s -u $TWILIO_ACCOUNT_SID:$TWILIO_AUTH_TOKEN \
  https://trunking.twilio.com/v1/Trunks/TKxxxxxxxx | jq '.transfer_mode, .transfer_caller_id'

# write — a human runs this, deliberately, once
twilio api trunking v1 trunks update --sid TKxxxxxxxx \
  --transfer-mode enable-all --transfer-caller-id from-transferee
curl -X POST https://trunking.twilio.com/v1/Trunks/TKxxxxxxxx \
  --data-urlencode "TransferMode=enable-all" \
  --data-urlencode "TransferCallerId=from-transferee" \
  -u $TWILIO_ACCOUNT_SID:$TWILIO_AUTH_TOKEN
```

The same thing in the console: **Elastic SIP Trunking → Manage → Trunks →**
*the trunk* **→ Features → Call Transfer (SIP REFER) → Enabled**, then the
**Caller ID for Transfer Target** dropdown, then **Enable PSTN Transfer**, then
save. (Twilio's own docs describe the PSTN checkbox in prose without naming it;
those labels are LiveKit's, and they match the console as it stands.)

What Twilio documents about the SIP conversation, and what it does not:

- **Accepted:** *"Upon receiving the SIP REFER, Twilio returns a `202 Accepted`
  response"*, then `NOTIFY`s carrying `100 Trying` / `200 OK`. The transferor
  hangs up the original leg once the new one answers.
- **Refused: no documented response code.** The whole `call-transfer` page
  contains exactly two status codes and both are `202`. That a refused REFER
  comes back `603 Declined` is field evidence (livekit/sip#234 — same Twilio
  elastic trunk, closed with no published diagnosis), which is why
  `core/telephony/transfer.py` maps 603 to `rejected` and attaches a hint
  pointing here rather than asserting a cause.
- **Refer-To:** `tel:+34600111222` or `sip:+34600111222@<trunk>.pstn.twilio.com`
  — for PSTN the `sip:` form *must* use your Termination domain. We send the
  `tel:` form.
- **Not supported:** early media, and transfers to emergency numbers (911/933).
- **Billing:** the transferred leg is a **child call**. For an inbound
  (Origination) call transferred to the PSTN you are billed
  `Origination (A→B) × child duration` **plus** `Termination (B→C) × child
  duration` — i.e. double, for as long as the transferred call lasts.
- **Termination is very probably a requirement**, not just for warm. Twilio
  never says so outright, but the child leg is billed as Termination and the
  `sip:` Refer-To form needs the Termination domain. Treat a trunk with only
  Origination as untested for cold transfer, and read the SIP status the box
  reports rather than assuming.

**Warm transfer needs more than this.** It dials the colleague INTO the room
with `CreateSIPParticipant`, which is an *outbound* call and therefore needs a
Termination domain, credentials and a LiveKit `SIPOutboundTrunk` whose id goes
in `SIP_OUTBOUND_TRUNK_ID`. None of those exist on this box, so the warm verb
is refused at the door with a message naming the variable — never halfway
through a live call. Cold needs none of it.

```
TRANSFER_TO=+34600111222        # where a transfer goes when the desk names no number
TRANSFER_RINGING_S=25           # how long the far end rings (LiveKit's own default is 30)
SIP_OUTBOUND_TRUNK_ID=ST_…      # warm only; unset means warm is refused
```

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
- **A server-side unsubscribe is invisible to the client that was cut off.**
  The warm transfer needs the caller not to hear the briefing, and both ways of
  arranging that — `RoomService.UpdateSubscriptions(subscribe=False)` and the
  publisher's own `set_track_subscription_permissions` — **work** on
  livekit-server v1.9.1, even against a subscriber that joined with
  `autoSubscribe`. The first probe said neither worked, because it watched
  `track_subscribed` / `track_unsubscribed` on the cut-off participant: the
  Python SDK fires neither for a server-side revocation, the `AudioStream` just
  goes quiet, and the SFU logged `revoking subscription` the whole time.
  `scripts/isolation_probe.py` counts received audio frames instead, which is
  the only measurement that answers the question — run it against the dev
  compose and read the table. It also measures what the events could never
  have told you: **the cut takes about 220 ms per stream to bite**, which is
  the warm transfer's one remaining leak and is documented as such in
  `core/telephony/transfer.py`.
- **The routes table is a file.** `CONVO_DB` (default `tmp/convo.db`) is
  relative to the working directory: add the route and run the worker from
  the same directory, or the number has no route.

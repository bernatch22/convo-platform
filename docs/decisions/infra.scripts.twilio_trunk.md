# `infra.scripts.twilio_trunk`

The reasoning that used to live in the docstrings of `infra/scripts/twilio_trunk.py`; the code keeps one line per symbol.

## module

Four resources, in two systems, that together make a PSTN number ring our
convo.worker. Run it as often as you like: every step reads first and creates only
what is missing, so a second run prints the same ids and changes nothing.

    uv run python infra/scripts/twilio_trunk.py --number +14176743169 --dry-run
    uv run python infra/scripts/twilio_trunk.py --number +14176743169

    Twilio   Elastic SIP Trunk           the carrier side of the call
             └ Origination URI           sip:lk.bernardocastro.dev;transport=udp
             └ the number, attached      an attached number ignores its voice_url
    LiveKit  SIPInboundTrunk             `numbers` is what lets the INVITE in when
                                         `hide_inbound_port: true` drops the rest
             SIPDispatchRule             individual room `call-…`, agent `cc`

It also REPORTS the trunk's `transfer_mode` / `transfer_caller_id` — the two
properties that decide whether a cold transfer's SIP REFER is carried — and
prints the exact command to change them. It never changes them itself: that is
a human's call, with a billing consequence, and this repo does not mutate a
trunk's call settings after the fraud incident that wrote that rule.

The rule names **no tenant**: which business answers is `store.route(fleet,
number)`, wired with `python -m convo routes add` — a phone number is a route,
never a project. Two tenants on one trunk differ by one row in a table.

Credentials come from the environment (`TWILIO_ACCOUNT_SID` plus either
`TWILIO_AUTH_TOKEN` or `TWILIO_API_KEY`/`TWILIO_API_SECRET`, and
`LIVEKIT_URL`/`LIVEKIT_API_KEY`/`LIVEKIT_API_SECRET`), or from the dotenv files
named with `--twilio-env`. Nothing here ever prints a secret.

Open source note: swap the two constants below and this is a generic
"carrier number → LiveKit agent" bootstrap for any Twilio account.

## report_transfer

Cold transfer is the trunk's decision, not ours: `livekit-sip` sends the
REFER and Twilio either carries it or does not. The two properties that
decide it are read here and reported; **this script never writes them.**
Switching a trunk on is a deliberate human act with a billing consequence
(the transferred leg is charged as Termination on top of the Origination
that is still running), and after a fraud incident nothing in this repo
mutates a trunk's call settings on its own.

"""twilio_trunk.py — the phone path, from a Twilio number to a LiveKit dispatch rule.

Four resources, in two systems, that together make a PSTN number ring our
worker. Run it as often as you like: every step reads first and creates only
what is missing, so a second run prints the same ids and changes nothing.

    uv run python scripts/twilio_trunk.py --number +14176743169 --dry-run
    uv run python scripts/twilio_trunk.py --number +14176743169

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
"""

import argparse
import asyncio
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from dotenv import load_dotenv
from livekit import api

SIP_HOST = "lk.bernardocastro.dev"
ORIGINATION_URI = f"sip:{SIP_HOST};transport=udp"
TRUNK_NAME = "convo-platform"
LK_TRUNK_NAME = "convo-cc-inbound"
LK_RULE_NAME = "convo-cc-individual"
ROOM_PREFIX = "call-"
FLEET = os.getenv("FLEET", "cc")

# Twilio's signalling networks (twilio.com/docs/sip-trunking#ip-addresses-signaling).
# With these on the trunk, an INVITE from anywhere else is refused before auth.
TWILIO_SIGNALING_CIDRS = [
    "54.172.60.0/23",
    "54.244.51.0/24",
    "54.171.127.192/26",
    "35.156.191.128/25",
    "54.65.63.192/26",
    "54.169.127.128/26",
    "54.252.254.64/26",
    "177.71.206.192/26",
]

TWILIO_API = "https://api.twilio.com/2010-04-01"
TRUNKING_API = "https://trunking.twilio.com/v1"


def main(argv: list[str]) -> int:
    """Wire one number end to end, printing every resource id it read or created."""
    args = parse_args(argv)
    load_dotenv(override=False)  # the project's own .env wins over the files named below
    for path in args.twilio_env:
        load_dotenv(path, override=False)
    try:
        twilio = Twilio.from_env()
    except KeyError as missing:
        print(f"missing credential: {missing}", file=sys.stderr)
        return 2

    print(f"number   {args.number}")
    trunk = twilio_trunk(twilio, args)
    if trunk is None:
        return 1
    asyncio.run(livekit_side(args))
    print(f"\nroute    python -m convo routes add {FLEET} {args.number} <tenant> <project> voice")
    return 0


def twilio_trunk(twilio: "Twilio", args: argparse.Namespace) -> str | None:
    """Trunk, origination URI and number attachment on the carrier; returns the trunk SID."""
    existing = twilio.get(f"{TRUNKING_API}/Trunks?PageSize=50")["trunks"]
    trunk = find(existing, "friendly_name", args.trunk_name)
    if trunk is None:
        if args.dry_run:
            print(f"trunk    MISSING (would create {args.trunk_name!r})")
            return "dry-run"
        trunk = twilio.post(f"{TRUNKING_API}/Trunks", {"FriendlyName": args.trunk_name})
    sid = trunk["sid"]
    print(f"trunk    {sid}  {trunk['friendly_name']}")
    report_transfer(trunk)

    urls = twilio.get(f"{TRUNKING_API}/Trunks/{sid}/OriginationUrls")["origination_urls"]
    origination = find(urls, "sip_url", ORIGINATION_URI)
    if origination is None and not args.dry_run:
        origination = twilio.post(
            f"{TRUNKING_API}/Trunks/{sid}/OriginationUrls",
            {
                "FriendlyName": "convo-box",
                "SipUrl": ORIGINATION_URI,
                "Weight": "10",
                "Priority": "10",
                "Enabled": "true",
            },
        )
    where = origination["sid"] if origination else "MISSING"
    print(f"origin   {where}  {ORIGINATION_URI}")

    number = number_row(twilio, args.number)
    if number is None:
        print(f"number   {args.number} is not on this Twilio account", file=sys.stderr)
        return None
    if number.get("trunk_sid") == sid:
        print(f"attached {number['sid']}  already on this trunk")
    elif args.dry_run:
        print(f"attached MISSING (would attach {number['sid']})")
    else:
        attached = twilio.post(
            f"{TRUNKING_API}/Trunks/{sid}/PhoneNumbers", {"PhoneNumberSid": number["sid"]}
        )
        print(f"attached {attached['sid']}  voice_url is now ignored: the trunk owns the call")
    return sid


async def livekit_side(args: argparse.Namespace) -> None:
    """The inbound trunk that admits the number and the rule that opens a room per call."""
    async with api.LiveKitAPI() as lk:
        trunks = (await lk.sip.list_inbound_trunk(api.ListSIPInboundTrunkRequest())).items
        trunk = next((t for t in trunks if args.number in t.numbers), None)
        if trunk is None and not args.dry_run:
            trunk = await lk.sip.create_inbound_trunk(
                api.CreateSIPInboundTrunkRequest(
                    trunk=api.SIPInboundTrunkInfo(
                        name=LK_TRUNK_NAME,
                        numbers=[args.number],
                        allowed_addresses=TWILIO_SIGNALING_CIDRS,
                    )
                )
            )
        if trunk is None:
            print("lk trunk MISSING (would create)")
            return
        print(f"lk trunk {trunk.sip_trunk_id}  numbers={list(trunk.numbers)}")

        rules = (await lk.sip.list_dispatch_rule(api.ListSIPDispatchRuleRequest())).items
        rule = next((r for r in rules if trunk.sip_trunk_id in r.trunk_ids), None)
        if rule is None and not args.dry_run:
            rule = await lk.sip.create_dispatch_rule(dispatch_rule_request(trunk.sip_trunk_id))
        if rule is None:
            print("lk rule  MISSING (would create)")
            return
        print(f"lk rule  {rule.sip_dispatch_rule_id}  room {ROOM_PREFIX}*  agent {FLEET}")


def dispatch_rule_request(trunk_id: str) -> api.CreateSIPDispatchRuleRequest:
    """One room per caller, dispatching the fleet — and naming no tenant, by design."""
    return api.CreateSIPDispatchRuleRequest(
        name=LK_RULE_NAME,
        trunk_ids=[trunk_id],
        rule=api.SIPDispatchRule(
            dispatch_rule_individual=api.SIPDispatchRuleIndividual(room_prefix=ROOM_PREFIX)
        ),
        room_config=api.RoomConfiguration(agents=[api.RoomAgentDispatch(agent_name=FLEET)]),
    )


def report_transfer(trunk: dict) -> None:
    """Say whether this trunk will carry a SIP REFER — and print the fix, never run it.

    Cold transfer is the trunk's decision, not ours: `livekit-sip` sends the
    REFER and Twilio either carries it or does not. The two properties that
    decide it are read here and reported; **this script never writes them.**
    Switching a trunk on is a deliberate human act with a billing consequence
    (the transferred leg is charged as Termination on top of the Origination
    that is still running), and after a fraud incident nothing in this repo
    mutates a trunk's call settings on its own.
    """
    mode = trunk.get("transfer_mode", "?")
    caller_id = trunk.get("transfer_caller_id", "?")
    verdict = "REFER to PSTN allowed" if mode == "enable-all" else "cold transfer will FAIL"
    print(f"transfer {mode} / caller-id {caller_id}  →  {verdict}")
    if mode == "enable-all":
        return
    print("         enable it yourself — the exact call, never run from here:")
    print(f"           twilio api trunking v1 trunks update --sid {trunk['sid']} \\")
    print("             --transfer-mode enable-all --transfer-caller-id from-transferee")
    print("         or: Console → Elastic SIP Trunking → Manage → Trunks → <trunk> →")
    print("             Features → Call Transfer (SIP REFER) = Enabled, + Enable PSTN Transfer")


def number_row(twilio: "Twilio", number: str) -> dict | None:
    """The account's row for one E.164 number, or None when the account does not own it."""
    query = urllib.parse.urlencode({"PhoneNumber": number})
    numbers = f"{TWILIO_API}/Accounts/{twilio.account_sid}/IncomingPhoneNumbers.json"
    rows = twilio.get(f"{numbers}?{query}")["incoming_phone_numbers"]
    return rows[0] if rows else None


def find(rows: list[dict], key: str, value: str) -> dict | None:
    """The first row whose `key` equals `value` — how every step here stays idempotent."""
    return next((row for row in rows if row.get(key) == value), None)


def parse_args(argv: list[str]) -> argparse.Namespace:
    """`--number` is the only thing a second account would change."""
    parser = argparse.ArgumentParser(description="Wire a Twilio number into LiveKit SIP.")
    parser.add_argument("--number", required=True, help="E.164, e.g. +14176743169")
    parser.add_argument("--trunk-name", default=TRUNK_NAME)
    parser.add_argument("--dry-run", action="store_true", help="read everything, create nothing")
    parser.add_argument(
        "--twilio-env",
        action="append",
        default=[],
        help="dotenv file holding TWILIO_* (repeatable; the environment still wins)",
    )
    return parser.parse_args(argv)


@dataclass(frozen=True)
class Twilio:
    """The two REST calls this script needs, with basic auth and form bodies."""

    account_sid: str
    user: str
    password: str

    @classmethod
    def from_env(cls) -> "Twilio":
        """Auth token if there is one, API key/secret otherwise — Twilio accepts both."""
        sid = os.environ["TWILIO_ACCOUNT_SID"]
        token = os.getenv("TWILIO_AUTH_TOKEN")
        if token:
            return cls(sid, sid, token)
        return cls(sid, os.environ["TWILIO_API_KEY"], os.environ["TWILIO_API_SECRET"])

    def get(self, url: str) -> dict:
        """GET one resource or page as JSON."""
        return self._send(urllib.request.Request(url))

    def post(self, url: str, form: dict[str, str]) -> dict:
        """POST a form-encoded body — every Twilio write takes one."""
        body = urllib.parse.urlencode(form).encode()
        request = urllib.request.Request(url, data=body)
        request.add_header("Content-Type", "application/x-www-form-urlencoded")
        return self._send(request)

    def _send(self, request: urllib.request.Request) -> dict:
        pair = base64.b64encode(f"{self.user}:{self.password}".encode()).decode()
        request.add_header("Authorization", f"Basic {pair}")
        try:
            with urllib.request.urlopen(request, timeout=30) as reply:
                return json.load(reply)
        except urllib.error.HTTPError as refused:
            detail = refused.read().decode()[:300]
            raise SystemExit(f"twilio {refused.code}: {detail}") from refused


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

"""sip_probe.py — one real SIP INVITE at the box, to prove the phone path without a phone.

Decisions: docs/decisions/infra.scripts.sip_probe.md
"""

import argparse
import random
import re
import socket
import sys
import time

HOST = "34.58.189.131"
PORT = 5060
DOMAIN = "lk.bernardocastro.dev"
DIALLED = "+14176743169"
CALLER = "+34600111222"
HOLD_S = 25


def token(n: int = 10) -> str:
    """A hex string for the one-shot identifiers every SIP transaction needs."""
    return "".join(random.choice("0123456789abcdef") for _ in range(n))


def parse_args(argv: list[str]) -> argparse.Namespace:
    """The number to dial, who to be, and how long to stay on the line."""
    parser = argparse.ArgumentParser(description="Send one SIP INVITE and report what came back.")
    parser.add_argument("--host", default=HOST, help="the SIP server's address")
    parser.add_argument("--dialled", default=DIALLED, help="the number in the To: header")
    parser.add_argument("--caller", default=CALLER, help="the number in the From: header")
    parser.add_argument("--hold", type=float, default=HOLD_S, help="seconds before BYE")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    """INVITE, read the response, ACK, hold the call open, BYE. Exit 1 if it was refused."""
    args = parse_args(argv)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(3.0)
    sock.bind(("0.0.0.0", 0))
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    probe.connect((args.host, PORT))
    local_ip = probe.getsockname()[0]
    probe.close()
    local_port = sock.getsockname()[1]
    call_id, tag, branch = token(16), token(8), token(16)

    sdp = "\r\n".join(
        [
            "v=0",
            f"o=probe 0 0 IN IP4 {local_ip}",
            "s=probe",
            f"c=IN IP4 {local_ip}",
            "t=0 0",
            "m=audio 40000 RTP/AVP 0 101",
            "a=rtpmap:0 PCMU/8000",
            "a=rtpmap:101 telephone-event/8000",
            "a=sendrecv",
            "",
        ]
    )
    invite = "\r\n".join(
        [
            f"INVITE sip:{args.dialled}@{DOMAIN} SIP/2.0",
            f"Via: SIP/2.0/UDP {local_ip}:{local_port};branch=z9hG4bK{branch};rport",
            "Max-Forwards: 70",
            f'From: "probe" <sip:{args.caller}@{DOMAIN}>;tag={tag}',
            f"To: <sip:{args.dialled}@{DOMAIN}>",
            f"Call-ID: {call_id}@{local_ip}",
            "CSeq: 1 INVITE",
            f"Contact: <sip:probe@{local_ip}:{local_port}>",
            "Content-Type: application/sdp",
            f"Content-Length: {len(sdp)}",
            "",
            sdp,
        ]
    )
    print(f"→ INVITE sip:{args.dialled}@{DOMAIN} from {local_ip}:{local_port}")
    sock.sendto(invite.encode(), (args.host, PORT))

    ok = None
    deadline = time.time() + 12
    while time.time() < deadline:
        try:
            data, _ = sock.recvfrom(65535)
        except TimeoutError:
            continue
        head = data.decode(errors="replace").split("\r\n")[0]
        print(f"← {head}")
        if head.startswith("SIP/2.0 200"):
            ok = data.decode(errors="replace")
            break
        if re.match(r"SIP/2\.0 [4-6]\d\d", head):
            return 1
    if ok is None:
        print("no final response — the INVITE was dropped (hide_inbound_port + allow-list)")
        return 1

    to_tag = re.search(r"^To:.*;tag=([^\r\n;]+)", ok, re.M | re.I)
    contact = re.search(r"^Contact:\s*<([^>]+)>", ok, re.M | re.I)
    target = contact.group(1) if contact else f"sip:{args.dialled}@{DOMAIN}"
    ack = "\r\n".join(
        [
            f"ACK {target} SIP/2.0",
            f"Via: SIP/2.0/UDP {local_ip}:{local_port};branch=z9hG4bK{token(16)};rport",
            "Max-Forwards: 70",
            f'From: "probe" <sip:{args.caller}@{DOMAIN}>;tag={tag}',
            f"To: <sip:{args.dialled}@{DOMAIN}>;tag={to_tag.group(1) if to_tag else ''}",
            f"Call-ID: {call_id}@{local_ip}",
            "CSeq: 1 ACK",
            "Content-Length: 0",
            "",
            "",
        ]
    )
    sock.sendto(ack.encode(), (args.host, PORT))
    print(f"→ ACK — answered; holding {args.hold}s so the agent session starts")
    time.sleep(args.hold)

    bye = "\r\n".join(
        [
            f"BYE {target} SIP/2.0",
            f"Via: SIP/2.0/UDP {local_ip}:{local_port};branch=z9hG4bK{token(16)};rport",
            "Max-Forwards: 70",
            f'From: "probe" <sip:{args.caller}@{DOMAIN}>;tag={tag}',
            f"To: <sip:{args.dialled}@{DOMAIN}>;tag={to_tag.group(1) if to_tag else ''}",
            f"Call-ID: {call_id}@{local_ip}",
            "CSeq: 2 BYE",
            "Content-Length: 0",
            "",
            "",
        ]
    )
    sock.sendto(bye.encode(), (args.host, PORT))
    print("→ BYE")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

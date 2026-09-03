# `convo.telephony.lines`

The reasoning that used to live in the docstrings of `convo/telephony/lines.py`; the code keeps one line per symbol.

## module

A number is not a field of a project. It is a ROUTE — one row keyed by fleet
and dialled number, the same `routes` table `convo/session/router.py` reads when a call
arrives — so a project has zero, one or several lines, and the console has to
be able to say all three honestly. That is the whole reason this module exists:
before it, the number lived as a string in the web client's chrome, printed
under every tenant, which made two projects look like they shared a line when
only one of them was reachable by phone at all.

The store is where the mapping lives; the SIP dispatch rule on the box is what
actually routes the call. `seeded_lines()` reading `infra/seed/routes.json` is that rule written down so a fresh
database is not empty and honest-looking at the same time, and `seed` only ever
FILLS A GAP: a key already in the store is left exactly as the operator set it,
because the operator has seen the box more recently than this file has.

Nothing here assigns or buys a number. Assigning one means editing the
livekit-sip dispatch rule over the LiveKit API; buying one means a Twilio
purchase, which we do not automate — carrier automation is indistinguishable
from an account takeover, and it is the fastest way to lose a trunk.

## seed

Returns only what it actually wrote, so a caller can log a first run and
stay silent on every one after it. A key already present is never touched.

## _note

Three different truths, and a project owner reads them differently: no line
at all (the phone door is shut), a line this deploy answers, or a line
registered against another fleet, which is worse than none — the number
exists, somebody may be handing it out, and no call on it ever reaches this
process.

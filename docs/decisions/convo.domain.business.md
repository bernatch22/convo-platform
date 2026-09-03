# `convo.domain.business`

The reasoning that used to live in the docstrings of `convo/domain/business.py`; the code keeps one line per symbol.

## module

`convo/state/outcomes.py` answers *what did the platform do* — irreversible calls
counted off the append-only log, whose summaries were PII-filtered on the way
in and stay that way. That is the transactional reading, and it is the right
one for an auditor. It is the wrong one for the person running the contact
centre, who asked a much plainer question: **who is coming, when, with whom,
and is that booking still standing.**

That question is not answerable from the log, and deliberately so. The log
holds `appointment ap-20260904-1000-trau now 2026-09-04T10:00` because the
name was masked before it was written — the platform is not the place a
patient's name is stored. The reservation, name and all, lives where it has
always lived: in the BUSINESS system. So this module goes and asks it.

**The route.** `convo/api/reservations.py` → `convo.session.registry` → the tenant's own adapters. The
registry is the one door `convo/` is allowed to open onto `tenants/` (it imports
each in try/except, and `tests/test_core_isolation.py` keeps every other file
in `convo/` honest). From there it is one capability, `LIST_RECORDS`, declared by
EVERY adapter that has a view to offer — a shop keeps its orders in one system
and its incidents in another, and those are two tables and not a longer one.
Nothing here knows what a clinic books or a shop ships: each adapter answers
with its own shape, its own labels and its own state words, and a tenant whose
systems have none answers `shape: null`, which the console shows as an honest
empty rather than a fake agenda.

**The join, and what it is for.** Each row's STATE comes from the business
system, because the business system is the authority on its own records — a
rescheduling is one cancel plus one booking to the platform, but it is *one
moved appointment* to the clinic, and only the clinic's own book can say so.
What the business system cannot know is which CONVERSATION produced the change
and whether the caller's yes was on record. That is exactly what the log has,
so the two are joined here.

The key is the appointment id, and the reason it works is a happy consequence
of the PII rule: an identifier is not a person, so it survives the mask and
lands in the log's summary verbatim (`appointment ap-… now …`). A business row
is matched to the newest transaction whose summary mentions its id; the row
then carries the session it came from, the verb that ran, and whether a
`confirm.granted` stood unspent before it. A substring match on an opaque id
is loose in principle — this is documented so nobody mistakes it for a foreign
key — and it is exact in practice because ids are minted from the slot they
book. A row nothing in the window mentions simply has no call behind it: it
was already on the book before we ever rang, and it says so with a dash.

The window is the same `days` the Board's counters use, so what the strip
counts and what the table links to cannot come from two different periods.

## _ask

One system used to answer and the rest were never asked, which was right
while a business had one kind of record. It stopped being right the moment
a shop kept orders in one system and incidents in another: the second view
is not a longer table, it is a DIFFERENT table — its own shape, its own
column headings, its own words for a state — and merging the two would have
meant `convo/` deciding which of the business's vocabularies wins. So the read
returns them all and the console draws one table each.

The flat `shape`/`labels`/`rows` of the answer stay the first view. Not
politeness towards an old client: it is what the endpoint has always meant
by "this project's records", the reason the tenant's factory order is
documented as meaning something, and it keeps a one-system tenant's answer
byte-for-byte what it was.

Adapters are built the way a session builds them — the tenant's own factory
— and thrown away when this read is over: a console read must not be able
to leave anything behind in a customer's system.

## _by_id

Rows arrive newest first, so the first mention of an id wins and the ones
behind it are the history of a record the table shows one line of.

## _identifier_in

A summary is prose a tool's own renderer wrote, so this cannot parse it. It
can do the one thing that is safe: an id is minted from a slot and always
reads `ap-20260904-1000-trau` or `TS-10432`, so a token with a hyphen or a
digit in it and no space is a candidate and everything else is language.

## _ordered

Two orderings in one table because the operator reads it for two reasons.
A booking that just happened is the thing they came to check, so it leads
however far away the appointment itself is; everything the platform never
touched is the standing book, and a book reads soonest-first.

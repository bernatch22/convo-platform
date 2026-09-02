"""`convo routes`: which tenant answers which phone number (or room key) on a fleet."""

from convo.state.store import Route, SQLiteStore, Store
from convo.telephony import lines

USAGE = (
    "usage: python -m convo routes list | seed | add <fleet> <key> <tenant> <project> [voice|chat]"
)
HEADER = f"{'fleet':<8} {'key':<18} {'tenant/project':<36} channel"


def main(argv: list[str], store: Store | None = None) -> int:
    """`list` prints every route; `seed` writes the deploy's known lines; `add` registers one."""
    store = store or SQLiteStore()
    if argv[:1] == ["list"]:
        return list_routes(store)
    if argv[:1] == ["seed"]:
        return seed_routes(store)
    if argv[:1] == ["add"] and len(argv) in (5, 6):
        channel = argv[5] if len(argv) == 6 else "voice"
        store.add_route(Route(argv[1], argv[2], argv[3], argv[4], channel))
        print(f"route {argv[2]} on {argv[1]} -> {argv[3]}/{argv[4]} ({channel})")
        return 0
    print(USAGE)
    return 2


def list_routes(store: Store) -> int:
    """One line per route, sorted by fleet and key."""
    print(HEADER)
    for route in store.routes():
        who = f"{route.tenant}/{route.project}"
        print(f"{route.fleet:<8} {route.key:<18} {who:<36} {route.channel}")
    return 0


def seed_routes(store: Store) -> int:
    """Write the numbers this deployment owns, skipping every key already stored.

    The same seed `api.py` runs at startup, by hand — for a laptop that never
    starts the control plane and still wants the console to tell the truth.
    """
    written = lines.seed(store)
    if not written:
        print("nothing to seed: every known line is already a route")
        return 0
    for route in written:
        print(f"seeded {route.key} on {route.fleet} -> {route.tenant}/{route.project}")
    return 0

"""`convo versions`: pin the prompt version a project serves, with or without an override."""

import pathlib

from convo.state.store import ProjectVersion, SQLiteStore, Store

USAGE = "usage: python -m convo versions list | pin <tenant> <project> <version> [<knowledge-file>]"
HEADER = f"{'tenant/project':<36} {'version':<16} override"


def main(argv: list[str], store: Store | None = None) -> int:
    """`list` prints every pin; `pin` sets one, optionally with a knowledge block from a file."""
    store = store or SQLiteStore()
    if argv[:1] == ["list"]:
        return list_versions(store)
    if argv[:1] == ["pin"] and len(argv) in (4, 5):
        override = pathlib.Path(argv[4]).read_text() if len(argv) == 5 else None
        store.pin_version(ProjectVersion(argv[1], argv[2], argv[3], override))
        print(f"{argv[1]}/{argv[2]} pinned to {argv[3]}" + (" with override" if override else ""))
        return 0
    print(USAGE)
    return 2


def list_versions(store: Store) -> int:
    """One line per pinned project: version and whether it overrides the git seed."""
    print(HEADER)
    for pin in store.versions():
        who = f"{pin.tenant}/{pin.project}"
        size = f"{len(pin.knowledge_override)} chars" if pin.knowledge_override else "-"
        print(f"{who:<36} {pin.version:<16} {size}")
    return 0

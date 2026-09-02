"""Prompt views: a Markdown file per stage, with `{% include "_partials/x.md" %}` lines expanded."""

import re
from pathlib import Path

INCLUDE = re.compile(r'^\{%\s*include\s+"([^"]+)"\s*%\}$', re.MULTILINE)


def render(root: Path, name: str) -> str:
    """The text of `root/<name>.md` with every include line replaced by that partial's text."""
    text = (root / f"{name}.md").read_text()
    return INCLUDE.sub(lambda match: partial(root, match.group(1)), text)


def partial(root: Path, name: str) -> str:
    """One shared paragraph, rendered recursively, without the newline the file ends with."""
    return render(root, name.removesuffix(".md")).rstrip("\n")


def includes(root: Path, name: str) -> list[str]:
    """The partials a view includes, in order: what a test pins about a prompt's composition."""
    return [m.group(1) for m in INCLUDE.finditer((root / f"{name}.md").read_text())]

"""The layout every stage prompt is rendered in: knowledge first, the view, then the protocols.

Decisions: docs/decisions/convo.prompting.layout.md
"""

from convo.domain.context import TenantContext
from convo.prompting.protocols import SUPERVISOR_PROTOCOL
from convo.prompting.render import render
from convo.telephony import human


def stage_prompt(tc: TenantContext, view: str) -> str:
    """One stage's system prompt: the knowledge block, its `prompts/<view>.md`, the protocols."""
    project = tc.project
    tag = project.knowledge_tag
    return "\n".join(
        [
            f"<{tag}>",
            project.knowledge(tc),
            f"</{tag}>",
            "",
            render(project.prompts, view),
            human.protocol(project),
            SUPERVISOR_PROTOCOL,
        ]
    )


def prompt(tc: TenantContext, name: str) -> str:
    """Any other prompt of the project by name, e.g. `confirm/move`: what ConfirmTask asks with."""
    return render(tc.project.prompts, name)

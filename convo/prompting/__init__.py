"""How a prompt is rendered: a layout, a Markdown view per stage, partials, and the cache floor."""

from convo.prompting.layout import prompt, stage_prompt
from convo.prompting.render import includes, render

__all__ = ["includes", "prompt", "render", "stage_prompt"]

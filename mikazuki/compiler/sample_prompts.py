from typing import List

from .models import SampleDraft


def format_sample_prompts(sample: SampleDraft) -> str:
    lines: List[str] = []
    for item in sample.prompts:
        prompt = item.prompt.strip()
        if not prompt:
            continue

        # sd-scripts reads one prompt per line and expands literal \n escapes.
        # Keep textarea line breaks inside the same prompt, including negatives.
        parts = [_escape_line_breaks(prompt)]
        if item.negativePrompt:
            parts.extend(["--n", _escape_line_breaks(item.negativePrompt)])
        if item.width:
            parts.extend(["--w", str(item.width)])
        if item.height:
            parts.extend(["--h", str(item.height)])
        if item.steps:
            parts.extend(["--s", str(item.steps)])
        if item.seed is not None:
            parts.extend(["--d", str(item.seed)])
        if item.cfgScale is not None:
            parts.extend(["--l", str(item.cfgScale)])
        if item.guidanceScale is not None:
            parts.extend(["--g", str(item.guidanceScale)])
        lines.append(" ".join(parts))
    return "\n".join(lines) + ("\n" if lines else "")


def _escape_line_breaks(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")

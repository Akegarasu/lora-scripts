from typing import List

from .models import SampleDraft


def format_sample_prompts(sample: SampleDraft) -> str:
    lines: List[str] = []
    for item in sample.prompts:
        prompt = item.prompt.strip()
        if not prompt:
            continue

        parts = [prompt]
        if item.negativePrompt:
            parts.extend(["--n", item.negativePrompt])
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

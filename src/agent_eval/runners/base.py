"""Public extension contract. Runners generate files; graders own the tests."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from agent_eval.specs import TaskSpec


@dataclass(frozen=True)
class Generation:
    raw_output: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None


class RunnerError(Exception):
    """A sanitized generation failure, optionally including partial output."""

    def __init__(self, message: str, *, raw_output: str = "", timed_out: bool = False) -> None:
        super().__init__(message)
        self.raw_output = raw_output
        self.timed_out = timed_out


class Runner(Protocol):
    async def generate(self, task: TaskSpec, workdir: Path) -> Generation: ...


class RunnerFactory(Protocol):
    def __call__(self, options: dict[str, Any], *, task_path: Path) -> Runner: ...


def extract_code(reply: str) -> str:
    """Prefer Python fences, then unlabeled fences; preserve unfenced source."""
    blocks = re.findall(r"^[ \t]*(`{3,}|~{3,})([^\n]*)\n(.*?)^\s*\1\s*$", reply, re.M | re.S)
    for labels in ({"python", "py", "python3"}, {""}):
        selected = [body for _, label, body in blocks if label.strip().lower() in labels]
        if selected:
            return "\n\n".join(body.strip("\n") for body in selected) + "\n"
    if blocks:
        raise RunnerError("reply contains no Python or unlabeled code block", raw_output=reply)
    # Some endpoints truncate the final closing fence.
    opening = re.search(r"^\s*(?:`{3,}|~{3,})(?:python3?|py)?\s*\n", reply, re.M)
    code = reply[opening.end() :] if opening else reply
    if not code.strip():
        raise RunnerError("model returned empty code", raw_output=reply)
    return code.strip("\n") + "\n"


def generation_prompt(task: TaskSpec) -> str:
    return (
        f"Implement this Python task in {task.entrypoint}. Use only the Python standard library.\n"
        "Return the complete source code in a single Python code block.\n\n" + task.prompt
    )

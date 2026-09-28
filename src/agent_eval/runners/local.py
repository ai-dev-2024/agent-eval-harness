from __future__ import annotations

import shlex
import string
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator

from agent_eval.process import run_process
from agent_eval.runners.base import Generation, RunnerError
from agent_eval.specs import PositiveSeconds, StrictModel, TaskSpec, task_file


class CLIOptions(StrictModel):
    command: list[str] | str
    timeout_s: PositiveSeconds = 120

    @field_validator("command")
    @classmethod
    def valid_command(cls, value: list[str] | str) -> list[str]:
        parts = shlex.split(value) if isinstance(value, str) else value
        if not parts or not parts[0]:
            raise ValueError("command cannot be empty")
        for part in parts:
            for _, name, fmt, conversion in string.Formatter().parse(part):
                if name is not None and (
                    name not in {"prompt_file", "workdir", "entrypoint"} or fmt or conversion
                ):
                    raise ValueError("unsupported command placeholder")
        return parts


class CLIRunner:
    def __init__(self, options: dict[str, Any]) -> None:
        self.options = CLIOptions.model_validate(options)

    async def generate(self, task: TaskSpec, workdir: Path) -> Generation:
        prompt_file = workdir / "_agent_prompt.txt"
        prompt_file.write_text(
            f"Write your Python implementation to {task.entrypoint}.\n\n{task.prompt}",
            encoding="utf-8",
        )
        command = self.options.command
        assert isinstance(command, list)
        args = [
            part.format(
                prompt_file=str(prompt_file), workdir=str(workdir), entrypoint=task.entrypoint
            )
            for part in command
        ]
        try:
            result = await run_process(args, workdir, self.options.timeout_s)
        except OSError as exc:
            raise RunnerError(f"cannot start agent command: {type(exc).__name__}") from exc
        if result.timed_out:
            raise RunnerError("agent timed out", raw_output=result.output, timed_out=True)
        if result.returncode:
            raise RunnerError(
                f"agent exited with code {result.returncode}", raw_output=result.output
            )
        return Generation(result.output)


class MockOptions(StrictModel):
    variant: Literal["reference", "wrong"] = "reference"
    fixtures: dict[str, str] = Field(default_factory=dict)


class MockRunner:
    def __init__(self, options: dict[str, Any], *, task_path: Path) -> None:
        self.options = MockOptions.model_validate(options)
        self.task_path = task_path

    async def generate(self, task: TaskSpec, workdir: Path) -> Generation:
        if self.options.variant == "wrong":
            code = (
                "# Deliberately wrong offline fixture.\n"
                "def __getattr__(name):\n    return lambda *args, **kwargs: None\n"
            )
        else:
            filename = self.options.fixtures.get(task.id, task.reference)
            code = task_file(self.task_path, filename).read_text(encoding="utf-8")
        (workdir / task.entrypoint).write_text(code, encoding="utf-8")
        return Generation(code)

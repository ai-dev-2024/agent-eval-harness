"""Register custom runner factories before calling run_config()."""

from pathlib import Path
from typing import Any

from agent_eval.runners.base import Runner, RunnerFactory
from agent_eval.runners.http import HTTPRunner
from agent_eval.runners.local import CLIRunner, MockRunner

_REGISTRY: dict[str, RunnerFactory] = {}


def register_runner(name: str, factory: RunnerFactory) -> None:
    if not name or name in _REGISTRY:
        raise ValueError(f"runner name is empty or already registered: {name}")
    _REGISTRY[name] = factory


def create_runner(name: str, options: dict[str, Any], *, task_path: Path) -> Runner:
    try:
        factory = _REGISTRY[name]
    except KeyError as exc:
        raise ValueError(f"unknown runner: {name}") from exc
    return factory(options, task_path=task_path)


def _openai(options: dict[str, Any], *, task_path: Path) -> Runner:
    return HTTPRunner(options)


def _anthropic(options: dict[str, Any], *, task_path: Path) -> Runner:
    return HTTPRunner(options, anthropic=True)


def _cli(options: dict[str, Any], *, task_path: Path) -> Runner:
    return CLIRunner(options)


register_runner("openai", _openai)
register_runner("anthropic", _anthropic)
register_runner("cli", _cli)
register_runner("mock", MockRunner)

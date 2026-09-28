from pathlib import Path
from typing import Any

import pytest
import yaml

from agent_eval.runners import create_runner, register_runner
from agent_eval.runners.local import CLIOptions, MockRunner
from agent_eval.specs import RunConfig, discover_tasks, load_config, load_task, task_file


def test_load_discover_and_defaults(task_path: Path, config_path: Path) -> None:
    spec = load_task(task_path, require_reference=True)
    assert spec.language == "python" and spec.reference == "reference.py"
    assert spec.tags == []
    config = load_config(config_path)
    assert config.repeats == 2 and config.concurrency == 2
    assert discover_tasks(config.tasks * 2, config_path.parent) == [(task_path, spec)]


@pytest.mark.parametrize(
    "change",
    [
        {"id": "../bad"},
        {"entrypoint": "../solution.py"},
        {"entrypoint": "conftest.py"},
        {"language": "other"},
        {"timeout_s": 0},
        {"timeout_s": float("inf")},
        {"hidden_tests": []},
        {"hidden_tests": ["hidden.py", "hidden.py"]},
        {"hidden_tests": ["missing.py"]},
        {"unknown": True},
    ],
)
def test_invalid_task(task_path: Path, change: dict[str, Any]) -> None:
    data = yaml.safe_load(task_path.read_text())
    data.update(change)
    task_path.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError):
        load_task(task_path)


def test_task_path_boundaries(task_path: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.py"
    outside.write_text("pass")
    (task_path.parent / "link.py").symlink_to(outside)
    for filename in ("../outside.py", str(outside), "link.py", "missing.py"):
        with pytest.raises(ValueError):
            task_file(task_path, filename)
    (task_path.parent / "reference.py").unlink()
    load_task(task_path)
    with pytest.raises(ValueError):
        load_task(task_path, require_reference=True)


def test_discovery_rejects_duplicates_and_missing(task_path: Path) -> None:
    with pytest.raises(ValueError, match="matched no"):
        discover_tasks(["absent/*.yaml"], task_path.parent)
    (task_path.parent / "duplicate.yaml").write_text(task_path.read_text())
    with pytest.raises(ValueError, match="ids must be unique"):
        discover_tasks(["*.yaml"], task_path.parent)


@pytest.mark.parametrize("field,value", [("repeats", 0), ("concurrency", -1), ("repeats", True)])
def test_invalid_config(config_path: Path, field: str, value: int) -> None:
    data = yaml.safe_load(config_path.read_text())
    data[field] = value
    with pytest.raises(ValueError):
        RunConfig.model_validate(data)
    data["models"] *= 2
    with pytest.raises(ValueError):
        RunConfig.model_validate(data)


@pytest.mark.parametrize("command", ["", [], ["echo", "{bad}"], ["echo", "{workdir!r}"]])
def test_invalid_command(command: list[str] | str) -> None:
    with pytest.raises(ValueError):
        CLIOptions(command=command)


def test_registry(task_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown runner"):
        create_runner("nonexistent", {}, task_path=task_path)
    with pytest.raises(ValueError, match="already registered"):
        register_runner("mock", MockRunner)
    options = {"model": "test", "api_key_env": "KEY", "base_url_env": "BASE"}
    for runner in ("anthropic", "openai"):
        assert create_runner(runner, options, task_path=task_path)
    assert create_runner("cli", {"command": "echo {entrypoint}"}, task_path=task_path)


def test_discovery_treats_config_directory_literally(task_path: Path, tmp_path: Path) -> None:
    base = tmp_path / "check[out]"
    base.mkdir()
    found = discover_tasks([str(Path("..") / task_path.relative_to(tmp_path))], base)
    assert [path for path, _ in found] == [task_path.resolve()]
    assert discover_tasks([str(task_path)], base)[0][1].id == "answer"

"""Strict file formats and deterministic task discovery."""

from __future__ import annotations

import glob
import re
from pathlib import Path
from typing import Annotated, Any, Literal, TypeVar

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

PositiveSeconds = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TaskSpec(StrictModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")
    title: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    language: Literal["python"] = "python"
    entrypoint: str
    hidden_tests: list[str] = Field(min_length=1)
    reference: str = "reference.py"
    timeout_s: PositiveSeconds = 10
    tags: list[str] = Field(default_factory=list)

    @field_validator("entrypoint")
    @classmethod
    def valid_entrypoint(cls, value: str) -> str:
        if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]*\.py", value):
            raise ValueError("entrypoint must be a plain Python module filename")
        if value in {"conftest.py", "pytest.py", "sitecustomize.py", "usercustomize.py"}:
            raise ValueError("entrypoint collides with test infrastructure")
        return value


class ModelSpec(StrictModel):
    name: str = Field(min_length=1)
    runner: str = Field(min_length=1)
    options: dict[str, Any] = Field(default_factory=dict)


class RunConfig(StrictModel):
    models: list[ModelSpec] = Field(min_length=1)
    tasks: list[str] = Field(min_length=1)
    repeats: int = Field(default=1, ge=1, strict=True)
    concurrency: int = Field(default=1, ge=1, strict=True)

    @field_validator("models")
    @classmethod
    def unique_names(cls, value: list[ModelSpec]) -> list[ModelSpec]:
        if len({item.name for item in value}) != len(value):
            raise ValueError("model names must be unique")
        return value


_Model = TypeVar("_Model", bound=BaseModel)


def read_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def _parse(model: type[_Model], path: Path) -> _Model:
    try:
        return model.model_validate(read_yaml(path))
    except (ValidationError, yaml.YAMLError) as exc:
        exc.add_note(f"in {path}")
        raise


def load_config(path: Path) -> RunConfig:
    return _parse(RunConfig, path)


def task_file(task_path: Path, filename: str) -> Path:
    """Reject missing files and paths/symlinks outside the task directory."""
    root = task_path.resolve().parent
    candidate = (root / filename).resolve()
    if Path(filename).is_absolute() or not candidate.is_relative_to(root):
        raise ValueError(f"task file must stay inside its directory: {filename}")
    if not candidate.is_file():
        raise ValueError(f"missing task file: {filename}")
    return candidate


def load_task(path: Path, *, require_reference: bool = False) -> TaskSpec:
    spec = _parse(TaskSpec, path)
    if len(set(spec.hidden_tests)) != len(spec.hidden_tests):
        raise ValueError("hidden_tests contains duplicates")
    for filename in spec.hidden_tests:
        task_file(path, filename)
    if require_reference:
        task_file(path, spec.reference)
    return spec


def discover_tasks(patterns: list[str], base: Path) -> list[tuple[Path, TaskSpec]]:
    paths: set[Path] = set()
    for pattern in patterns:
        # root_dir keeps glob metacharacters in the config's own path from being expanded.
        found = glob.glob(pattern, root_dir=base, recursive=True)
        matches = [(base / p).resolve() for p in found]
        if not matches:
            raise ValueError(f"task glob matched no files: {pattern}")
        paths.update(matches)
    tasks = [(path, load_task(path)) for path in sorted(paths)]
    if len({task.id for _, task in tasks}) != len(tasks):
        raise ValueError("task ids must be unique")
    return tasks

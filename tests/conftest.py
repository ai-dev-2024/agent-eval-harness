from pathlib import Path

import pytest
import yaml


@pytest.fixture
def task_path(tmp_path: Path) -> Path:
    directory = tmp_path / "task"
    directory.mkdir()
    (directory / "hidden.py").write_text(
        "from solution import answer\ndef test_answer():\n    assert answer() == 42\n"
    )
    (directory / "reference.py").write_text("def answer():\n    return 42\n")
    path = directory / "task.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "id": "answer",
                "title": "Return an answer",
                "prompt": "Implement answer() returning 42.",
                "entrypoint": "solution.py",
                "hidden_tests": ["hidden.py"],
                "timeout_s": 3,
            }
        )
    )
    return path


@pytest.fixture
def workdir(tmp_path: Path) -> Path:
    directory = tmp_path / "work"
    directory.mkdir()
    return directory


@pytest.fixture
def config_path(task_path: Path, tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "models": [
                    {"name": "correct", "runner": "mock"},
                    {"name": "wrong", "runner": "mock", "options": {"variant": "wrong"}},
                ],
                "tasks": [str(task_path.relative_to(tmp_path))],
                "repeats": 2,
                "concurrency": 2,
            }
        )
    )
    return path

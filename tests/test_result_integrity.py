"""Imported results must not silently inflate a comparison's sample count."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_eval.results import Attempt, load_attempts, summarize


def row(identity: str, **updates: object) -> Attempt:
    return Attempt.model_validate(
        {
            "attempt_id": identity,
            "model": "model",
            "runner": "mock",
            "task_id": "task",
            "repeat": 1,
            "outcome": "pass",
            "tests_passed": 1,
            "tests_total": 1,
            "wall_time_s": 0,
            "generation_time_s": 0,
            "grading_time_s": 0,
            "artifacts": "attempts/one",
            **updates,
        }
    )


def test_passed_count_cannot_exceed_total() -> None:
    with pytest.raises(ValidationError, match="passed test count exceeds"):
        row("one", tests_passed=2)


def test_duplicate_repeat_rejected_on_import(tmp_path: Path) -> None:
    target = tmp_path / "results.jsonl"
    target.write_text(row("one").model_dump_json() + "\n" + row("two").model_dump_json())
    with pytest.raises(ValueError, match="duplicate model/task/repeat on line 2"):
        load_attempts(target)


def test_duplicates_rejected_by_library_summary() -> None:
    with pytest.raises(ValueError, match="duplicate attempt id"):
        summarize([row("one"), row("one", repeat=2)])
    with pytest.raises(ValueError, match="duplicate model/task/repeat"):
        summarize([row("one"), row("two")])


def test_repeat_identity_is_scoped_to_model_and_task(tmp_path: Path) -> None:
    rows = [row("one"), row("two", model="other"), row("three", task_id="other")]
    target = tmp_path / "results.jsonl"
    target.write_text("\n".join(item.model_dump_json() for item in rows))
    assert load_attempts(target) == rows
    assert summarize(rows).attempts == 3

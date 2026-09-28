import itertools
import json
from pathlib import Path
from typing import cast

import pytest

from agent_eval.grader import Outcome
from agent_eval.report import ReportFormat, render_report
from agent_eval.results import Attempt, load_attempts, pass_at_k, summarize


def attempt(
    index: int, task: str = "task", outcome: Outcome = "pass", model: str = "model"
) -> Attempt:
    return Attempt(
        attempt_id=str(index),
        model=model,
        runner="mock",
        task_id=task,
        repeat=index + 1,
        outcome=outcome,
        wall_time_s=float(index),
        generation_time_s=0,
        grading_time_s=0,
        artifacts=f"attempts/{index}",
    )


def test_pass_at_k_matches_enumeration() -> None:
    for n in range(1, 9):
        for c in range(n + 1):
            for k in range(1, n + 1):
                draws = list(itertools.combinations(range(n), k))
                expected = sum(any(value < c for value in draw) for draw in draws) / len(draws)
                assert pass_at_k(n, c, k) == pytest.approx(expected)
    assert pass_at_k(10**9, 1, 1) == pytest.approx(1e-9, rel=1e-10)


@pytest.mark.parametrize("values", [(0, 0, 1), (3, 4, 1), (3, -1, 1), (3, 1, 0), (3, 1, 4)])
def test_invalid_k(values: tuple[int, int, int]) -> None:
    with pytest.raises(ValueError):
        pass_at_k(*values)


def test_summary_macro_average_and_partial_usage() -> None:
    rows = [attempt(0), attempt(1, outcome="fail"), attempt(2, "other", "timeout")]
    rows[0] = rows[0].model_copy(update={"input_tokens": 0, "output_tokens": 12, "cost_usd": 0.0})
    result = summarize(rows).models[0]
    assert result.pass_at_1 == 0.25  # Per-task mean, not the pooled 1/3 rate.
    assert result.pass_at_k == {1: 0.25}  # Task "other" cannot support k=2.
    assert result.mean_wall_time_s == result.median_wall_time_s == 1
    assert result.input_tokens == 0 and result.output_tokens == 12 and result.cost_usd == 0
    assert result.cost_reported == 1 and result.outcomes["timeout"] == 1
    assert summarize([attempt(0)]).models[0].input_tokens is None
    with pytest.raises(ValueError):
        summarize([])
    with pytest.raises(ValueError):
        summarize(rows, (0,))


@pytest.mark.parametrize("format", ["md", "html", "json"])
def test_reports_escape_text_and_include_data(format: str) -> None:
    rows = [
        attempt(0, model='<script>alert("x")</script>|model'),
        attempt(1, "other", model="second"),
    ]
    summary = summarize(rows)
    rendered = render_report(summary, cast(ReportFormat, format))
    if format == "json":
        assert json.loads(rendered)["attempts"] == 2
    else:
        assert "<script>" not in rendered and "&lt;script&gt;" in rendered
        assert "unknown" in rendered and "—" in rendered
    if format == "html":
        assert "<svg" in rendered and "<rect" in rendered
        assert "<style>" in rendered
        assert "<script" not in rendered and "http" not in rendered
        assert "Leaderboard" in rendered and "Per-task pass matrix" in rendered
    if format == "md":
        assert "&#124;" in rendered
    with pytest.raises(ValueError):
        render_report(summary, cast(ReportFormat, "bad"))


def test_jsonl_validation(tmp_path: Path) -> None:
    path = tmp_path / "results.jsonl"
    row = attempt(0)
    path.write_text(row.model_dump_json() + "\n\n")
    assert load_attempts(path) == [row]
    for content, message in [
        ("", "no attempts"),
        ("{}", "line 1"),
        (row.model_dump_json().replace('"1.0"', '"2.0"'), "line 1"),
        ((row.model_dump_json() + "\n") * 2, "duplicate"),
    ]:
        path.write_text(content)
        with pytest.raises(ValueError, match=message):
            load_attempts(path)

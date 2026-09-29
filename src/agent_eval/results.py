"""Versioned attempts and task-macro-averaged comparison statistics."""

from __future__ import annotations

import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Literal

from pydantic import Field

from agent_eval.grader import Outcome
from agent_eval.specs import StrictModel


class Attempt(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    attempt_id: str
    model: str
    runner: str
    task_id: str
    repeat: int = Field(ge=1)
    outcome: Outcome
    tests_passed: int = Field(default=0, ge=0)
    tests_total: int = Field(default=0, ge=0)
    wall_time_s: float = Field(ge=0, allow_inf_nan=False)
    generation_time_s: float = Field(ge=0, allow_inf_nan=False)
    grading_time_s: float = Field(ge=0, allow_inf_nan=False)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    error: str | None = None
    artifacts: str


class TaskScore(StrictModel):
    task_id: str
    attempts: int
    passed: int
    pass_at_1: float


class ModelSummary(StrictModel):
    model: str
    attempts: int
    passed: int
    outcomes: dict[str, int]
    pass_at_1: float
    pass_at_k: dict[int, float]
    mean_wall_time_s: float
    median_wall_time_s: float
    wall_times_s: list[float]
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    input_tokens_reported: int
    output_tokens_reported: int
    cost_reported: int
    tasks: list[TaskScore]


class Summary(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    attempts: int
    task_ids: list[str]
    models: list[ModelSummary]


def pass_at_k(n: int, c: int, k: int) -> float:
    """Unbiased estimator: 1 - choose(n-c, k) / choose(n, k)."""
    if not 0 <= c <= n or not 1 <= k <= n:
        raise ValueError("require 0 <= c <= n and 1 <= k <= n")
    if n - c < k:
        return 1.0
    # Stable when c/n is small; avoid subtracting nearly equal floating values.
    return -math.expm1(sum(math.log1p(-c / (n - i)) for i in range(k)))


def load_attempts(path: Path) -> list[Attempt]:
    attempts: list[Attempt] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8") as stream:
        for index, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                attempt = Attempt.model_validate_json(line)
            except ValueError as exc:
                raise ValueError(f"invalid attempt on line {index}") from exc
            if attempt.attempt_id in seen:
                raise ValueError(f"duplicate attempt id on line {index}")
            seen.add(attempt.attempt_id)
            attempts.append(attempt)
    if not attempts:
        raise ValueError("results contain no attempts")
    return attempts


def summarize(attempts: list[Attempt], ks: tuple[int, ...] = (1, 2, 5, 10)) -> Summary:
    if not attempts or any(k < 1 for k in ks):
        raise ValueError("need attempts and positive k values")
    grouped: dict[str, list[Attempt]] = defaultdict(list)
    for attempt in attempts:
        grouped[attempt.model].append(attempt)
    models: list[ModelSummary] = []
    for model, items in sorted(grouped.items()):
        tasks: dict[str, list[Attempt]] = defaultdict(list)
        for item in items:
            tasks[item.task_id].append(item)
        scores = []
        for task, rows in sorted(tasks.items()):
            passed = sum(row.outcome == "pass" for row in rows)
            scores.append(
                TaskScore(
                    task_id=task, attempts=len(rows), passed=passed, pass_at_1=passed / len(rows)
                )
            )
        estimates = {
            k: statistics.mean(pass_at_k(s.attempts, s.passed, k) for s in scores)
            for k in sorted(set(ks) | {1})
            if all(s.attempts >= k for s in scores)
        }
        times = [row.wall_time_s for row in items]
        ins = [row.input_tokens for row in items if row.input_tokens is not None]
        outs = [row.output_tokens for row in items if row.output_tokens is not None]
        costs = [row.cost_usd for row in items if row.cost_usd is not None]
        models.append(
            ModelSummary(
                model=model,
                attempts=len(items),
                passed=sum(s.passed for s in scores),
                outcomes={
                    state: sum(r.outcome == state for r in items)
                    for state in ("pass", "fail", "error", "timeout")
                },
                pass_at_1=estimates[1],
                pass_at_k=estimates,
                mean_wall_time_s=statistics.mean(times),
                median_wall_time_s=statistics.median(times),
                wall_times_s=times,
                input_tokens=sum(ins) if ins else None,
                output_tokens=sum(outs) if outs else None,
                cost_usd=sum(costs) if costs else None,
                input_tokens_reported=len(ins),
                output_tokens_reported=len(outs),
                cost_reported=len(costs),
                tasks=scores,
            )
        )
    models.sort(key=lambda m: (-m.pass_at_1, m.mean_wall_time_s, m.model))
    return Summary(
        attempts=len(attempts), task_ids=sorted({r.task_id for r in attempts}), models=models
    )


def summary_json(summary: Summary) -> str:
    return json.dumps(summary.model_dump(mode="json"), indent=2) + "\n"

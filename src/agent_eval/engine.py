"""Async orchestration and durable, credential-redacted run artifacts."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import platform
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

import yaml

from agent_eval import __version__
from agent_eval.grader import Grade, grade
from agent_eval.report import render_report
from agent_eval.results import Attempt, summarize
from agent_eval.runners import create_runner
from agent_eval.runners.base import Generation, Runner, RunnerError
from agent_eval.specs import TaskSpec, discover_tasks, load_config, load_task, task_file


async def validate_task(path: Path) -> Grade:
    task = load_task(path, require_reference=True)
    with tempfile.TemporaryDirectory(prefix="agent-eval-validate-") as directory:
        workdir = Path(directory)
        (workdir / task.entrypoint).write_bytes(task_file(path, task.reference).read_bytes())
        return await grade(task, path, workdir)


async def run_config(config_path: Path, out: Path) -> list[Attempt]:
    config_path = config_path.resolve()
    config = load_config(config_path)
    tasks = discover_tasks(config.tasks, config_path.parent)
    # Validate every runner before creating a run directory or starting any generation.
    jobs: list[tuple[str, str, Path, TaskSpec, int, Runner]] = []
    for model in config.models:
        for task_path, task in tasks:
            for repeat in range(1, config.repeats + 1):
                runner = create_runner(model.runner, model.options, task_path=task_path)
                jobs.append((model.name, model.runner, task_path, task, repeat, runner))
    secrets = [
        os.environ[value]
        for model in config.models
        for name, value in model.options.items()
        if name == "api_key_env" and isinstance(value, str) and os.environ.get(value)
    ]

    def redact(value: str) -> str:
        for secret in sorted(secrets, key=len, reverse=True):
            value = value.replace(secret, "[REDACTED]")
        return value

    out = out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    resolved = config.model_dump(mode="json")
    resolved["tasks"] = [str(path) for path, _ in tasks]
    (out / "config.resolved.yaml").write_text(
        redact(yaml.safe_dump(resolved, sort_keys=False)), encoding="utf-8"
    )
    hashes: dict[str, dict[str, str]] = {}
    for path, task in tasks:
        sources = [path, *(task_file(path, name) for name in task.hidden_tests)]
        if (path.parent / task.reference).is_file():
            sources.append(task_file(path, task.reference))
        hashes[task.id] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    metadata = {
        "schema_version": "1.0",
        "harness_version": __version__,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "started_at": datetime.now(UTC).isoformat(),
        "task_hashes": hashes,
        "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
    }
    (out / "metadata.json").write_text(
        redact(json.dumps(metadata, indent=2)) + "\n", encoding="utf-8"
    )
    semaphore = asyncio.Semaphore(config.concurrency)
    attempts: list[Attempt] = []
    with (out / "results.jsonl").open("w", encoding="utf-8") as stream:

        async def execute(index: int, job: tuple[str, str, Path, TaskSpec, int, Runner]) -> None:
            async with semaphore:
                model_name, runner_name, task_path, task, repeat, runner = job
                attempt_id = f"attempt-{index:06d}"
                artifact_dir = out / "attempts" / attempt_id
                artifact_dir.mkdir(parents=True)
                start = time.perf_counter()
                generation_end = start
                grading_time = 0.0
                generated = Generation("")
                graded = Grade("error")
                error: str | None = None
                with tempfile.TemporaryDirectory(prefix="agent-eval-") as directory:
                    workdir = Path(directory)
                    try:
                        generated = await runner.generate(task, workdir)
                        generation_end = time.perf_counter()
                        graded = await grade(task, task_path, workdir)
                        grading_time = time.perf_counter() - generation_end
                    except RunnerError as exc:
                        generation_end = time.perf_counter()
                        generated = Generation(exc.raw_output)
                        graded = Grade("timeout" if exc.timed_out else "error")
                        error = str(exc)
                    except Exception as exc:
                        generation_end = time.perf_counter()
                        error = f"attempt failed: {type(exc).__name__}"
                    entrypoint = workdir / task.entrypoint
                    if entrypoint.is_file() and not entrypoint.is_symlink():
                        (artifact_dir / "solution.py").write_text(
                            redact(entrypoint.read_text(encoding="utf-8", errors="replace")),
                            encoding="utf-8",
                        )
                (artifact_dir / "model-output.txt").write_text(
                    redact(generated.raw_output), encoding="utf-8"
                )
                (artifact_dir / "test.log").write_text(redact(graded.log), encoding="utf-8")
                attempt = Attempt(
                    attempt_id=attempt_id,
                    model=redact(model_name),
                    runner=runner_name,
                    task_id=task.id,
                    repeat=repeat,
                    outcome=graded.outcome,
                    tests_passed=graded.passed,
                    tests_total=graded.total,
                    wall_time_s=time.perf_counter() - start,
                    generation_time_s=generation_end - start,
                    grading_time_s=grading_time,
                    input_tokens=generated.input_tokens,
                    output_tokens=generated.output_tokens,
                    cost_usd=generated.cost_usd,
                    error=redact(error) if error else None,
                    artifacts=str(artifact_dir.relative_to(out)),
                )
                stream.write(attempt.model_dump_json() + "\n")
                stream.flush()
                attempts.append(attempt)

        # Structured concurrency ensures cleanup completes before the result stream closes.
        async with asyncio.TaskGroup() as group:
            for index, job in enumerate(jobs, 1):
                group.create_task(execute(index, job))
    attempts.sort(key=lambda row: row.attempt_id)
    summary = summarize(attempts)
    (out / "summary.json").write_text(render_report(summary, "json"), encoding="utf-8")
    (out / "report.html").write_text(render_report(summary, "html"), encoding="utf-8")
    return attempts

import asyncio
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from agent_eval.cli import main
from agent_eval.engine import run_config
from agent_eval.results import load_attempts
from agent_eval.runners import register_runner
from agent_eval.runners.base import Generation, Runner, RunnerError
from agent_eval.specs import TaskSpec


def test_cli_end_to_end(
    config_path: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "run"
    assert main(["run", str(config_path), "--out", str(out)]) == 0
    assert "4 attempts; 2 passed" in capsys.readouterr().out
    rows = load_attempts(out / "results.jsonl")
    assert {r.outcome for r in rows} == {"pass", "fail"}
    assert len({row.attempt_id for row in rows}) == 4
    for row in rows:
        assert row.wall_time_s >= row.generation_time_s + row.grading_time_s
        for filename in ("model-output.txt", "test.log", "solution.py"):
            assert (out / row.artifacts / filename).is_file()
    metadata = json.loads((out / "metadata.json").read_text())
    assert metadata["harness_version"] == "1.0.0"
    for files in metadata["task_hashes"].values():
        for path, digest in files.items():
            assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
    resolved = yaml.safe_load((out / "config.resolved.yaml").read_text())
    assert all(Path(p).is_absolute() for p in resolved["tasks"])
    for format in ("md", "html", "json"):
        target = tmp_path / f"report.{format}"
        assert (
            main(
                [
                    "report",
                    str(out / "results.jsonl"),
                    "--format",
                    format,
                    "--out",
                    str(target),
                    "--k",
                    "2",
                ]
            )
            == 0
        )
        assert target.stat().st_size > 100
    assert main(["report", str(out / "results.jsonl")]) == 0
    assert "| correct | 100.0%" in capsys.readouterr().out
    assert main(["run", str(config_path), "--out", str(out)]) == 2
    assert "FileExistsError" in capsys.readouterr().err


def test_cli_listing_validation_and_errors(
    task_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["list-tasks", str(task_path)]) == 0
    assert "answer\tReturn an answer" in capsys.readouterr().out
    assert main(["validate-task", str(task_path)]) == 0
    assert "pass: 1/1" in capsys.readouterr().out
    (task_path.parent / "reference.py").write_text("def answer(): return 0")
    assert main(["validate-task", str(task_path)]) == 1
    assert "assert 0 == 42" in capsys.readouterr().err
    assert main(["report", str(task_path / "missing")]) == 2
    capsys.readouterr()
    result = subprocess.run(
        [sys.executable, "-m", "agent_eval", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "1.0.0"


def test_default_output(config_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["run", str(config_path)]) == 0
    assert len(list((tmp_path / "runs").glob("*/report.html"))) == 1


def test_runner_failures_and_redaction(
    task_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "a-unique-secret-value"
    monkeypatch.setenv("CUSTOM_SECRET", secret)
    active = 0
    peak = 0
    workdirs: set[Path] = set()

    class InstrumentedRunner:
        def __init__(self, mode: str) -> None:
            self.mode = mode

        async def generate(self, task: TaskSpec, workdir: Path) -> Generation:
            nonlocal active, peak
            assert not list(workdir.iterdir())
            workdirs.add(workdir)
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.02)
            active -= 1
            if self.mode == "timeout":
                raise RunnerError("timeout " + secret, raw_output=secret, timed_out=True)
            if self.mode == "error":
                raise RuntimeError(secret)
            (workdir / task.entrypoint).write_text("def answer(): return 42\n# " + secret)
            return Generation(secret, 3, 4, 0.1)

    def factory(options: dict[str, Any], *, task_path: Path) -> Runner:
        return InstrumentedRunner(str(options["mode"]))

    register_runner("instrumented", factory)
    config = tmp_path / "instrumented.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "models": [
                    {
                        "name": mode,
                        "runner": "instrumented",
                        "options": {"mode": mode, "api_key_env": "CUSTOM_SECRET"},
                    }
                    for mode in ("pass", "timeout", "error")
                ],
                "tasks": [str(task_path)],
                "repeats": 2,
                "concurrency": 2,
            }
        )
    )
    out = tmp_path / "observed"
    rows = asyncio.run(run_config(config, out))
    assert len(workdirs) == 6 and peak == 2
    assert all(not p.exists() for p in workdirs)
    assert {r.outcome for r in rows} == {"pass", "timeout", "error"}
    assert [r for r in rows if r.outcome == "pass"][0].input_tokens == 3
    for path in out.rglob("*"):
        if path.is_file():
            assert secret not in path.read_text()


def test_invalid_runner_fails_before_output(config_path: Path, tmp_path: Path) -> None:
    data = yaml.safe_load(config_path.read_text())
    data["models"][0]["runner"] = "absent"
    config_path.write_text(yaml.safe_dump(data))
    out = tmp_path / "not-created"
    with pytest.raises(ValueError, match="unknown runner"):
        asyncio.run(run_config(config_path, out))
    assert not out.exists()

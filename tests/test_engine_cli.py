import asyncio
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from agent_eval import __version__
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
    assert metadata["harness_version"] == __version__
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
    assert f"agent-eval: File exists: {out}" in capsys.readouterr().err


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
    assert result.stdout.strip() == __version__


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


def test_custom_fixture_is_hashed(config_path: Path, task_path: Path, tmp_path: Path) -> None:
    fixture = task_path.parent / "custom.py"
    fixture.write_text("def answer(): return 42\n")
    data = yaml.safe_load(config_path.read_text())
    data["models"] = [
        {"name": "fixture", "runner": "mock", "options": {"fixtures": {"answer": "custom.py"}}}
    ]
    data["repeats"] = 1
    config_path.write_text(yaml.safe_dump(data))
    out = tmp_path / "fixture-run"
    rows = asyncio.run(run_config(config_path, out))
    assert rows[0].outcome == "pass"
    metadata = json.loads((out / "metadata.json").read_text())
    assert (
        metadata["task_hashes"]["answer"][str(fixture)]
        == hashlib.sha256(fixture.read_bytes()).hexdigest()
    )


def test_cli_errors_are_specific_without_echoing_values(
    config_path: Path, task_path: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    literal = "sk-literal-key-in-config"
    config = tmp_path / "literal.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "models": [{"name": "m", "runner": "openai", "options": {"api_key": literal}}],
                "tasks": [str(task_path)],
            }
        )
    )
    assert main(["run", str(config), "--out", str(tmp_path / "unused")]) == 2
    err = capsys.readouterr().err
    assert "invalid HTTPOptions" in err and "api_key: Extra inputs are not permitted" in err
    assert literal not in err
    task_path.write_text(task_path.read_text().replace("solution.py", "../solution.py"))
    assert main(["run", str(config_path), "--out", str(tmp_path / "unused")]) == 2
    err = capsys.readouterr().err
    assert "invalid TaskSpec: entrypoint:" in err and f"in {task_path}" in err
    config.write_text("models: [\n")
    assert main(["run", str(config), "--out", str(tmp_path / "unused")]) == 2
    assert "invalid YAML at line 2, column 1" in capsys.readouterr().err
    assert main(["report", str(tmp_path / "absent.jsonl")]) == 2
    assert "No such file or directory" in capsys.readouterr().err
    assert not (tmp_path / "unused").exists()


def test_invalid_result_from_custom_runner_exits_cleanly(
    task_path: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    class BadUsageRunner:
        async def generate(self, task: TaskSpec, workdir: Path) -> Generation:
            (workdir / task.entrypoint).write_text("def answer(): return 42\n")
            return Generation("", input_tokens=-1)

    register_runner("bad-usage", lambda options, *, task_path: BadUsageRunner())
    config = tmp_path / "bad-usage.yaml"
    config.write_text(
        yaml.safe_dump(
            {"models": [{"name": "m", "runner": "bad-usage"}], "tasks": [str(task_path)]}
        )
    )
    assert main(["run", str(config), "--out", str(tmp_path / "out")]) == 2
    assert "invalid Attempt: input_tokens:" in capsys.readouterr().err


def test_describe_error_branches() -> None:
    from pydantic import ValidationError

    from agent_eval.cli import describe_error
    from agent_eval.specs import RunConfig

    assert describe_error(ValueError("unknown runner: x")) == "unknown runner: x"
    assert describe_error(yaml.YAMLError("secret-ish detail")) == "invalid YAML"
    assert describe_error(PermissionError(13, "Permission denied")) == "Permission denied"
    with pytest.raises(ValidationError) as caught:
        RunConfig.model_validate({f"extra{i}": "secret-value" for i in range(7)})
    message = describe_error(caught.value)
    assert message.startswith("invalid RunConfig: ") and message.endswith("; and 4 more")
    assert "secret-value" not in message

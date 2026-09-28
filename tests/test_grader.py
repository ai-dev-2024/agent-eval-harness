import asyncio
import os
import sys
from pathlib import Path

import pytest

from agent_eval.engine import validate_task
from agent_eval.grader import grade, parse_junit
from agent_eval.process import run_process
from agent_eval.specs import load_task


@pytest.mark.parametrize(
    "source,outcome,passed,total",
    [
        ("def answer(): return 42", "pass", 1, 1),
        ("def answer(): return 0", "fail", 0, 1),
        ("syntax error !", "error", 0, 1),
        ("def answer():\n    while True: pass", "timeout", 0, 0),
    ],
)
def test_grade_outcomes(
    task_path: Path, workdir: Path, source: str, outcome: str, passed: int, total: int
) -> None:
    task = load_task(task_path).model_copy(update={"timeout_s": 0.7})
    (workdir / task.entrypoint).write_text(source)
    result = asyncio.run(grade(task, task_path, workdir))
    assert result.outcome == outcome, result.log
    assert (result.passed, result.total) == (passed, total)
    assert not list(workdir.glob("_hidden_*"))


def test_missing_and_symlink_entrypoint(task_path: Path, workdir: Path) -> None:
    task = load_task(task_path)
    assert asyncio.run(grade(task, task_path, workdir)).outcome == "error"
    (workdir / task.entrypoint).symlink_to(task_path.parent / "reference.py")
    assert asyncio.run(grade(task, task_path, workdir)).outcome == "error"


def test_grader_ignores_generated_config_and_does_not_inherit_secrets(
    task_path: Path, workdir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SECRET_FOR_TEST", "do-not-inherit")
    (workdir / "solution.py").write_text(
        "import os\nassert 'SECRET_FOR_TEST' not in os.environ\ndef answer(): return 42"
    )
    (workdir / "conftest.py").write_text("raise RuntimeError('must not load')")
    (workdir / "pytest.py").write_text("raise RuntimeError('must not load')")
    (workdir / "pytest.ini").write_text("[pytest]\naddopts = --no-such-option\n")
    result = asyncio.run(grade(load_task(task_path), task_path, workdir))
    assert result.outcome == "pass", result.log


@pytest.mark.parametrize(
    "xml,code,outcome,passed,total",
    [
        ("invalid", 0, "error", 0, 0),
        ("<testsuites/>", 5, "error", 0, 0),
        ("<testsuite><testcase/><testcase><skipped/></testcase></testsuite>", 0, "fail", 1, 2),
        ("<testsuite><testcase><failure/></testcase></testsuite>", 1, "fail", 0, 1),
        ("<testsuite><testcase><error/></testcase></testsuite>", 2, "error", 0, 1),
        ("<testsuite><testcase/></testsuite>", 3, "error", 1, 1),
    ],
)
def test_junit(tmp_path: Path, xml: str, code: int, outcome: str, passed: int, total: int) -> None:
    path = tmp_path / "result.xml"
    path.write_text(xml)
    result = parse_junit(path, code, "log")
    assert (result.outcome, result.passed, result.total) == (outcome, passed, total)


@pytest.mark.parametrize("task_path", sorted(Path("tasks").glob("*/task.yaml")))
def test_example_reference(task_path: Path) -> None:
    result = asyncio.run(validate_task(task_path))
    assert result.outcome == "pass", result.log
    assert result.passed >= 10


@pytest.mark.skipif(os.name != "posix", reason="process-group semantics are POSIX-specific")
def test_timeout_kills_descendants(tmp_path: Path) -> None:
    marker = tmp_path / "orphan.txt"
    child = "import time,pathlib; time.sleep(0.6); pathlib.Path('orphan.txt').touch()"
    parent = (
        f"import subprocess,time,sys; subprocess.Popen([sys.executable,'-c',{child!r}]); "
        "time.sleep(10)"
    )

    async def run() -> None:
        result = await run_process([sys.executable, "-c", parent], tmp_path, 0.2)
        assert result.timed_out
        await asyncio.sleep(0.7)
        assert not marker.exists()

    asyncio.run(run())


def test_cancellation_cleans_up(tmp_path: Path) -> None:
    async def run() -> None:
        task = asyncio.create_task(
            run_process([sys.executable, "-c", "import time; time.sleep(30)"], tmp_path, 30)
        )
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())

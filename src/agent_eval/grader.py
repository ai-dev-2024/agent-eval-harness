"""Withhold tests until generation ends, then grade in a fresh subprocess."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from agent_eval.process import run_process
from agent_eval.specs import TaskSpec, task_file

Outcome = Literal["pass", "fail", "error", "timeout"]


@dataclass(frozen=True)
class Grade:
    outcome: Outcome
    passed: int = 0
    total: int = 0
    log: str = ""


def parse_junit(path: Path, returncode: int, log: str) -> Grade:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return Grade("error", log=log + "\nMissing or invalid test result XML.")
    cases = list(root.iter("testcase"))
    errors = sum(case.find("error") is not None for case in cases)
    passed = sum(
        all(case.find(tag) is None for tag in ("error", "failure", "skipped")) for case in cases
    )
    if errors or returncode not in (0, 1) or not cases:
        outcome: Outcome = "error"
    elif returncode == 0 and passed == len(cases):
        outcome = "pass"
    else:
        outcome = "fail"
    return Grade(outcome, passed, len(cases), log)


async def grade(task: TaskSpec, task_path: Path, workdir: Path) -> Grade:
    entrypoint = workdir / task.entrypoint
    if entrypoint.is_symlink() or not entrypoint.is_file():
        return Grade("error", log="Entrypoint is missing or is a symlink.")
    with tempfile.TemporaryDirectory(prefix="_hidden_", dir=workdir) as hidden:
        test_dir = Path(hidden)
        for index, filename in enumerate(task.hidden_tests):
            shutil.copyfile(task_file(task_path, filename), test_dir / f"test_{index:03d}.py")
        junit_path = test_dir / "results.xml"
        # Import the installed pytest before adding the generated source directory.
        # Disable generated config and plugins; this is not a security boundary.
        command = [
            sys.executable,
            "-I",
            "-c",
            "import os,sys,pytest; sys.path.insert(0,os.getcwd()); "
            "raise SystemExit(pytest.main(sys.argv[1:]))",
            "-q",
            "-p",
            "no:cacheprovider",
            "--noconftest",
            "--import-mode=importlib",
            "-c",
            os.devnull,
            "--rootdir",
            str(workdir),
            "--tb=short",
            f"--junitxml={junit_path}",
            str(test_dir),
        ]
        env = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "LANG") if key in os.environ}
        env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        result = await run_process(command, workdir, task.timeout_s, env)
        if result.timed_out:
            return Grade("timeout", log=result.output)
        return parse_junit(junit_path, result.returncode, result.output)

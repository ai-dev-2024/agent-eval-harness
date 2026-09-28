"""Async subprocesses with process-group cleanup on timeout and cancellation."""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    output: str
    timed_out: bool


async def run_process(
    command: list[str], cwd: Path, timeout_s: float, env: dict[str, str] | None = None
) -> ProcessResult:
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=cwd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=os.name == "posix",
    )

    def kill() -> None:
        with contextlib.suppress(ProcessLookupError):
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()

    reader = asyncio.create_task(process.communicate())
    timed_out = False
    try:
        output, _ = await asyncio.wait_for(asyncio.shield(reader), timeout_s)
    except TimeoutError:
        timed_out = True
        kill()
        output, _ = await reader
    except asyncio.CancelledError:
        kill()
        await reader
        raise
    finally:
        # A command can exit while leaving children running in its session.
        kill()
    return ProcessResult(process.returncode or 0, output.decode("utf-8", "replace"), timed_out)

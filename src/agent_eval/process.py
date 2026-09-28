"""Async subprocesses with process-group cleanup on timeout and cancellation."""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
from dataclasses import dataclass
from pathlib import Path

MAX_OUTPUT_BYTES = 1_000_000
# After the command exits, how long to wait for descendants outside its process group
# to release the output pipe before abandoning the remaining output.
DRAIN_GRACE_S = 1.0


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    output: str
    timed_out: bool


async def _drain(stream: asyncio.StreamReader, buffer: bytearray, limit: int) -> None:
    """Keep reading so writers never block, but retain at most ``limit`` bytes."""
    while chunk := await stream.read(65536):
        buffer.extend(chunk[: max(0, limit + 1 - len(buffer))])


async def run_process(
    command: list[str],
    cwd: Path,
    timeout_s: float,
    env: dict[str, str] | None = None,
    *,
    max_output_bytes: int = MAX_OUTPUT_BYTES,
) -> ProcessResult:
    """Run until the command itself exits or times out, then kill its process group.

    stdin is /dev/null. stdout and stderr share a pipe owned here rather than by asyncio,
    so a descendant that escapes the process group and keeps the pipe open cannot block
    ``Process.wait()`` or hang the harness.
    """
    posix = os.name == "posix"
    transport: asyncio.BaseTransport | None = None
    if posix:
        read_fd, write_fd = os.pipe()
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=cwd,
                env=env,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=write_fd,
                stderr=asyncio.subprocess.STDOUT,
                start_new_session=True,
            )
        except BaseException:
            os.close(read_fd)
            raise
        finally:
            os.close(write_fd)
        stream = asyncio.StreamReader()
        transport, _ = await asyncio.get_running_loop().connect_read_pipe(
            lambda: asyncio.StreamReaderProtocol(stream), os.fdopen(read_fd, "rb", buffering=0)
        )
    else:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=cwd,
            env=env,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        assert process.stdout is not None
        stream = process.stdout

    def kill() -> None:
        with contextlib.suppress(ProcessLookupError):
            if posix:
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()

    buffer = bytearray()
    reader = asyncio.create_task(_drain(stream, buffer, max_output_bytes))
    timed_out = False
    try:
        try:
            await asyncio.wait_for(process.wait(), timeout_s)
        except TimeoutError:
            timed_out = True
        # A command can exit while leaving children running in its session.
        kill()
        await process.wait()
        await asyncio.wait([reader], timeout=DRAIN_GRACE_S)
    except asyncio.CancelledError:
        kill()
        await process.wait()
        raise
    finally:
        kill()
        reader.cancel()
        if transport is not None:
            transport.close()
    output = buffer[:max_output_bytes].decode("utf-8", "replace")
    if len(buffer) > max_output_bytes:
        output += f"\n[agent-eval: output truncated after {max_output_bytes} bytes]\n"
    return ProcessResult(process.returncode or 0, output, timed_out)

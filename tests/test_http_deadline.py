import asyncio
from pathlib import Path

import httpx
import pytest

from agent_eval.runners.base import RunnerError
from agent_eval.runners.http import HTTPRunner
from agent_eval.specs import load_task


def test_http_wall_deadline(
    task_path: Path, workdir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TEST_KEY", "fixture-key")
    monkeypatch.setenv("TEST_BASE", str(httpx.URL(scheme="https", host="endpoint.invalid")))
    cancelled = False

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal cancelled
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled = True
            raise
        return httpx.Response(200)  # pragma: no cover

    runner = HTTPRunner(
        {
            "model": "test",
            "base_url_env": "TEST_BASE",
            "api_key_env": "TEST_KEY",
            "timeout_s": 0.05,
        },
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(RunnerError) as caught:
        asyncio.run(runner.generate(load_task(task_path), workdir))
    assert caught.value.timed_out and cancelled


@pytest.mark.parametrize("write_error", [False, True])
def test_failed_extraction_or_write_retains_reported_usage(
    task_path: Path, workdir: Path, monkeypatch: pytest.MonkeyPatch, write_error: bool
) -> None:
    monkeypatch.setenv("TEST_KEY", "fixture-key")
    monkeypatch.setenv("TEST_BASE", str(httpx.URL(scheme="https", host="endpoint.invalid")))
    raw = "pass" if write_error else "```json\n{}\n```"
    if write_error:
        (workdir / "solution.py").mkdir()
    runner = HTTPRunner(
        {"model": "test", "base_url_env": "TEST_BASE", "api_key_env": "TEST_KEY"},
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": raw}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 20},
                },
            )
        ),
    )
    with pytest.raises(RunnerError) as caught:
        asyncio.run(runner.generate(load_task(task_path), workdir))
    assert caught.value.generation.input_tokens == 10
    assert caught.value.generation.output_tokens == 20
    assert caught.value.raw_output == raw

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

from agent_eval.runners.base import RunnerError, extract_code
from agent_eval.runners.http import HTTPRunner
from agent_eval.runners.local import CLIRunner, MockRunner
from agent_eval.specs import load_task

BASE = str(httpx.URL(scheme="https", host="endpoint.invalid", path="/v1"))


@pytest.mark.parametrize(
    "reply,expected",
    [
        ("x = 1", "x = 1\n"),
        ("Here it is:\n```python\nx = 1\n```\nDone.", "x = 1\n"),
        ("```json\n{}\n```\n```py\nx = 1\n```", "x = 1\n"),
        ("```\nx = 1\n```", "x = 1\n"),
        ("~~~Python3\nx = 1\n~~~", "x = 1\n"),
        ("```python\nx = 1", "x = 1\n"),
        ("```python\nx = 1\n```\n```python\ny = 2\n```", "x = 1\n\ny = 2\n"),
    ],
)
def test_code_extraction(reply: str, expected: str) -> None:
    assert extract_code(reply) == expected


@pytest.mark.parametrize("reply", ["", "  ", "```json\n{}\n```", "```python\n \n```"])
def test_invalid_code(reply: str) -> None:
    with pytest.raises(RunnerError):
        extract_code(reply)


@pytest.mark.parametrize("anthropic", [False, True])
def test_http_success(
    anthropic: bool, task_path: Path, workdir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TEST_KEY", "secret-value")
    # A reserved invalid host; the transport intercepts every request.
    monkeypatch.setenv("TEST_BASE", BASE + "/")

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["model"] == "test-model"
        assert "answer()" in payload["messages"][0]["content"]
        assert "hidden" not in payload["messages"][0]["content"]
        assert payload["temperature"] == 0
        content = "```python\ndef answer():\n    return 42\n```"
        if anthropic:
            assert request.url.path == "/v1/messages"
            assert request.headers["x-api-key"] == "secret-value"
            assert request.headers["anthropic-version"] == "2023-06-01"
            body: dict[str, Any] = {
                "content": [{"type": "text", "text": content}],
                "usage": {"input_tokens": 10, "output_tokens": 20, "cost_usd": 0.01},
            }
        else:
            assert request.url.path == "/v1/chat/completions"
            assert request.headers["Authorization"] == "Bearer secret-value"
            body = {
                "choices": [{"message": {"content": content}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20, "cost_usd": 0.01},
            }
        return httpx.Response(200, json=body)

    runner = HTTPRunner(
        {
            "model": "test-model",
            "base_url_env": "TEST_BASE",
            "api_key_env": "TEST_KEY",
            "temperature": 0,
        },
        anthropic=anthropic,
        transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(runner.generate(load_task(task_path), workdir))
    assert result.input_tokens == 10 and result.output_tokens == 20
    assert result.cost_usd == 0.01
    assert (workdir / "solution.py").read_text() == "def answer():\n    return 42\n"


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"choices": []},
        {"choices": [{"message": {"content": None}}]},
        {"choices": [{"message": {"content": "pass"}}], "usage": {"prompt_tokens": -1}},
        {"choices": [{"message": {"content": "pass"}}], "usage": {"cost_usd": -1}},
        {"choices": [{"message": {"content": "pass"}}], "usage": {"cost_usd": "free"}},
    ],
)
def test_invalid_http_responses(
    body: dict[str, Any], task_path: Path, workdir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TEST_KEY", "secret-value")
    monkeypatch.setenv("TEST_BASE", BASE)
    runner = HTTPRunner(
        {"model": "test", "base_url_env": "TEST_BASE", "api_key_env": "TEST_KEY"},
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body)),
    )
    with pytest.raises(RunnerError, match="invalid response"):
        asyncio.run(runner.generate(load_task(task_path), workdir))


@pytest.mark.parametrize("mode", ["missing", "status", "timeout", "missing_usage", "invalid_json"])
def test_http_error_and_unknown_usage(
    mode: str, task_path: Path, workdir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TEST_KEY", raising=False)
    if mode != "missing":
        monkeypatch.setenv("TEST_KEY", "secret-value")
    monkeypatch.setenv("TEST_BASE", BASE)

    def handler(request: httpx.Request) -> httpx.Response:
        if mode == "timeout":
            raise httpx.ReadTimeout("secret-value", request=request)
        if mode == "status":
            return httpx.Response(401, text="secret-value")
        if mode == "invalid_json":
            return httpx.Response(200, text="not json")
        return httpx.Response(200, json={"choices": [{"message": {"content": "pass"}}]})

    runner = HTTPRunner(
        {"model": "test", "base_url_env": "TEST_BASE", "api_key_env": "TEST_KEY"},
        transport=httpx.MockTransport(handler),
    )
    if mode == "missing_usage":
        result = asyncio.run(runner.generate(load_task(task_path), workdir))
        assert result.input_tokens is result.output_tokens is result.cost_usd is None
    else:
        with pytest.raises(RunnerError) as caught:
            asyncio.run(runner.generate(load_task(task_path), workdir))
        assert "secret-value" not in str(caught.value)
        assert caught.value.timed_out == (mode == "timeout")


def test_cli_writes_files_without_hidden_tests(task_path: Path, workdir: Path) -> None:
    script = task_path.parent / "agent.py"
    script.write_text(
        "from pathlib import Path\nimport sys\n"
        "assert not list(Path.cwd().glob('*hidden*'))\n"
        "assert 'answer()' in Path(sys.argv[1]).read_text()\n"
        "Path(sys.argv[2]).write_text('def answer(): return 42')\nprint('generated')\n"
    )
    runner = CLIRunner({"command": [sys.executable, str(script), "{prompt_file}", "{entrypoint}"]})
    result = asyncio.run(runner.generate(load_task(task_path), workdir))
    assert result.raw_output == "generated\n"
    assert (workdir / "solution.py").is_file()


@pytest.mark.parametrize("timeout", [False, True])
def test_cli_failure(timeout: bool, task_path: Path, workdir: Path) -> None:
    code = (
        "import time; print('partial',flush=True); time.sleep(20)"
        if timeout
        else "raise SystemExit(7)"
    )
    runner = CLIRunner({"command": [sys.executable, "-c", code], "timeout_s": 0.2})
    with pytest.raises(RunnerError) as caught:
        asyncio.run(runner.generate(load_task(task_path), workdir))
    assert caught.value.timed_out == timeout
    if timeout:
        assert "partial" in caught.value.raw_output


def test_mock_custom_fixture(task_path: Path, workdir: Path) -> None:
    (task_path.parent / "custom.py").write_text("value = 123\n")
    runner = MockRunner({"fixtures": {"answer": "custom.py"}}, task_path=task_path)
    result = asyncio.run(runner.generate(load_task(task_path), workdir))
    assert result.raw_output == "value = 123\n"

"""Small vendor adapters with injectable transports and no SDK dependencies."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
from pydantic import Field

from agent_eval.runners.base import Generation, RunnerError, extract_code, generation_prompt
from agent_eval.specs import PositiveSeconds, StrictModel, TaskSpec


class HTTPOptions(StrictModel):
    model: str = Field(min_length=1)
    base_url_env: str = Field(min_length=1)
    api_key_env: str = Field(min_length=1)
    timeout_s: PositiveSeconds = 120
    max_tokens: int = Field(default=4096, ge=1)
    temperature: float | None = Field(default=None, ge=0, le=2, allow_inf_nan=False)


class HTTPRunner:
    def __init__(
        self,
        options: dict[str, Any],
        *,
        anthropic: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.options = HTTPOptions.model_validate(options)
        self.anthropic = anthropic
        self.transport = transport

    async def generate(self, task: TaskSpec, workdir: Path) -> Generation:
        opts = self.options
        base_url = os.environ.get(opts.base_url_env)
        key = os.environ.get(opts.api_key_env)
        if not base_url or not key:
            raise RunnerError("required API environment variable is missing")
        headers = (
            {"x-api-key": key, "anthropic-version": "2023-06-01"}
            if self.anthropic
            else {"Authorization": f"Bearer {key}"}
        )
        payload: dict[str, Any] = {
            "model": opts.model,
            "messages": [{"role": "user", "content": generation_prompt(task)}],
            "max_tokens": opts.max_tokens,
        }
        if opts.temperature is not None:
            payload["temperature"] = opts.temperature
        endpoint = "messages" if self.anthropic else "chat/completions"
        try:
            async with httpx.AsyncClient(
                timeout=opts.timeout_s, transport=self.transport, follow_redirects=False
            ) as client:
                response = await client.post(
                    base_url.rstrip("/") + "/" + endpoint, headers=headers, json=payload
                )
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise RunnerError("API request timed out", timed_out=True) from exc
        except (httpx.HTTPError, ValueError) as exc:
            # Never persist response bodies, URLs, headers, or credential-bearing exceptions.
            raise RunnerError("API request failed") from exc
        try:
            data = response.json()
            if self.anthropic:
                raw = "\n".join(p["text"] for p in data["content"] if p.get("type") == "text")
                in_key, out_key = "input_tokens", "output_tokens"
            else:
                raw = data["choices"][0]["message"]["content"]
                in_key, out_key = "prompt_tokens", "completion_tokens"
            if not isinstance(raw, str):
                raise ValueError("non-text response")
            usage = data.get("usage") or {}
            # Cost is deliberately not inferred from a pricing table.
            cost = usage.get("cost_usd")
            result = Generation(
                raw,
                _tokens(usage.get(in_key)),
                _tokens(usage.get(out_key)),
                _cost(cost),
            )
        except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
            raise RunnerError("API returned an invalid response") from exc
        (workdir / task.entrypoint).write_text(extract_code(raw), encoding="utf-8")
        return result


def _tokens(value: Any) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise ValueError("invalid token count")
    return int(value)


def _cost(value: Any) -> float | None:
    import math

    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("invalid cost")
    if value < 0 or not math.isfinite(value):
        raise ValueError("invalid cost")
    return float(value)

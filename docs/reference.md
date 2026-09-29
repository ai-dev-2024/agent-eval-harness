# Reference

- [Run config](#run-config)
- [Runners](#runners)
- [Writing a task](#writing-a-task)
- [Run directory and JSONL schema](#run-directory-and-jsonl-schema)
- [Outcomes and scoring](#outcomes-and-scoring)
- [CLI exit codes](#cli-exit-codes)
- [Library use and custom runners](#library-use-and-custom-runners)

## Run config

```yaml
models:
  - name: local-reference
    runner: mock
    options:
      variant: reference
tasks:
  - ../tasks/*/task.yaml
repeats: 2
concurrency: 2
```

| Field | Meaning |
| --- | --- |
| `models` | Nonempty list of `name`, registered `runner`, and runner-specific `options`. Names must be unique. |
| `tasks` | Nonempty list of task YAML globs, resolved relative to the config file. `**` is supported. Every glob must match; duplicate matches are merged; task ids must be unique. |
| `repeats` | Attempts per model × task. Default 1. |
| `concurrency` | Maximum simultaneous attempts (generation plus grading). Default 1. |

Unknown fields in the config and in built-in runner options are rejected.

## Runners

| Runner | Options |
| --- | --- |
| `openai` | Chat Completions-compatible endpoint. Required `model`, `base_url_env`, `api_key_env`; optional `max_tokens` (4096), `timeout_s` (120), `temperature` (omitted unless set). |
| `anthropic` | Messages API endpoint, version header `2023-06-01`. Same options. |
| `cli` | Required `command` (argv list or shell-like string); optional `timeout_s` (120). |
| `mock` | `variant`: `reference` (default) or `wrong`; optional `fixtures`: task id → task-relative Python file. |

### HTTP runners

`base_url_env` and `api_key_env` name environment variables; literal URLs and keys never go in
the config. The base URL must include the API version path; the runner appends
`/chat/completions` or `/messages`. Requests are non-streaming and `timeout_s` is a total
wall-clock deadline, not a per-read timeout. Redirects are not followed.

The prompt asks for one Python code block. `extract_code` in `runners/base.py` takes Python-labelled
fences first, then unlabelled fences, and tolerates a missing closing fence.

Token counts come from the response's `usage` object. Cost is recorded only if the response
includes `usage.cost_usd`; there is no pricing table. On HTTP errors the recorded error is the
status code only. Response bodies, headers and URLs are not saved.

See [`examples/real-models.yaml`](../examples/real-models.yaml) for a two-endpoint config.

### CLI runner

Arguments support the `{prompt_file}`, `{workdir}` and `{entrypoint}` placeholders; write literal
braces as `{{` and `}}`. No shell is launched, so pipes, redirection and `VAR=value` prefixes
are passed through literally. Prefer the argv-list form:

```yaml
models:
  - name: external-agent
    runner: cli
    options:
      command: [agent-command, --prompt-file, '{prompt_file}', --output, '{entrypoint}']
      timeout_s: 180
tasks: [../tasks/*/task.yaml]
```

The command runs with the fresh workdir as its cwd and must write the entrypoint file itself.
Its stdout/stderr are saved as `model-output.txt` but not treated as code. stdin is `/dev/null`.
A non-zero exit is recorded as an `error` attempt. On POSIX, anything left in the command's
process group is killed when it exits. The command inherits the parent environment so it can
authenticate. The grader subprocess gets only `PATH`, `SYSTEMROOT` and `LANG`.

### Mock runner

`reference` copies the task's `reference.py` (or the file named in `fixtures`) to the entrypoint.
`wrong` writes a module whose `__getattr__` returns a function that returns `None` for every name.
It exists to exercise the harness offline. It says nothing about any model.

## Writing a task

A task is a directory with `task.yaml`, `reference.py`, and one or more pytest files:

```yaml
id: answer
title: Return an answer
prompt: Implement answer() returning the integer 42.
language: python
entrypoint: solution.py
hidden_tests: [hidden_tests.py]
reference: reference.py
timeout_s: 5
tags: [intro, functions]
```

Defaults: `reference: reference.py`, `language: python` (the only supported value),
`timeout_s: 10`, `tags: []`. `entrypoint` must be a plain module filename and may not shadow
`conftest.py`, `pytest.py`, `sitecustomize.py` or `usercustomize.py`. Test and reference paths
must resolve inside the task directory, including through symlinks.

```python
# reference.py
def answer() -> int:
    return 42
```

```python
# hidden_tests.py
from solution import answer


def test_answer() -> None:
    assert answer() == 42
```

Check it with `agent-eval validate-task path/to/task.yaml`, which grades the reference exactly
as a generated solution would be graded.

Constraints to design around:

- Only the listed test files are copied, renamed to `test_000.py`, `test_001.py`, and so on. A
  shared `conftest.py`, data files and third-party pytest plugins are not available.
- Solutions and tests should need only the standard library.
- Put every error type and boundary rule the tests check into the prompt. The tests should
  check the stated contract, not requirements the prompt never mentions.

## Run directory and JSONL schema

```text
config.resolved.yaml          # config with task globs expanded to absolute paths
metadata.json                 # harness/Python versions, platform, start time, SHA-256 hashes
results.jsonl                 # one object per completed attempt, schema_version "1.0"
summary.json                  # same data as `agent-eval report --format json`
report.html
attempts/attempt-000001/
    model-output.txt          # model reply, or CLI stdout+stderr
    solution.py               # generated entrypoint, if one was written
    test.log                  # pytest stdout+stderr
```

`metadata.json` hashes the config, each task spec, its hidden tests, its reference (if present),
and any custom mock fixtures in use.

Each JSONL line has: `attempt_id`, `model`, `runner`, `task_id`, `repeat`, `outcome`,
`tests_passed`, `tests_total`, `wall_time_s`, `generation_time_s`, `grading_time_s`,
`input_tokens`, `output_tokens`, `cost_usd` (the last three nullable), `error`, and `artifacts`
(path relative to the run directory). Lines are appended and flushed as attempts complete, so
the file is in completion order. Attempt ids follow scheduling order and are deterministic for a
given config.

Every configured `api_key_env` value present in the environment is replaced with `[REDACTED]`
in all saved text. This is exact string matching on known keys, not a general secret scanner.

Output directories must not already exist. The harness never overwrites a previous run.

## Outcomes and scoring

| Outcome | Meaning |
| --- | --- |
| `pass` | pytest exited 0, at least one test ran, and every test case passed |
| `fail` | At least one failure, or skipped cases, so the suite did not fully pass |
| `error` | Generation failed, the entrypoint is missing, collection/setup error, or pytest crashed or produced no XML |
| `timeout` | Generation or grading exceeded its timeout; test counts are zero |

`tests_total` counts JUnit XML test cases, including skipped ones and collection errors. It is
not a count of assertions.

Pass@1 for a task is c/n over its attempts. Pass@k uses the unbiased estimator

```text
pass@k = 1 - C(n-c, k) / C(n, k),   1 <= k <= n
```

Both are averaged over tasks with equal weight (macro average). By default `report` shows
k ∈ {1, 2, 5, 10}, limited to values where every task for that model has at least k
attempts; pass `--k` one or more times to choose others. The estimator assumes attempts are
independent samples. That holds approximately for sampled API calls at nonzero temperature. It
does not hold for deterministic fixtures, or for agent sessions that share state.

If models were run on different task sets, their averages cover different tasks. The per-task
matrix shows `—` for missing cells.

Wall time covers generation plus grading and excludes time spent waiting for a concurrency slot.
With `concurrency > 1`, attempts compete for CPU, so it is not a clean latency measurement.

## CLI exit codes

| Code | When |
| --- | --- |
| 0 | Command completed. A `run` exits 0 even if every attempt failed. |
| 1 | `validate-task`: the reference did not pass |
| 2 | Invalid config, task, results file or arguments; I/O error |
| 130 | Interrupted. Lines already in `results.jsonl` remain valid. |

## Library use and custom runners

```python
import asyncio
from pathlib import Path

from agent_eval.engine import run_config
from agent_eval.report import render_report
from agent_eval.results import summarize

attempts = asyncio.run(run_config(Path("examples/mock-demo.yaml"), Path("runs/library-demo")))
markdown = render_report(summarize(attempts), "md")
```

A runner implements the `agent_eval.runners.base.Runner` protocol:

```python
async def generate(self, task: TaskSpec, workdir: Path) -> Generation: ...
```

It writes `task.entrypoint` into `workdir` and returns a `Generation` with the raw output and any
token and cost figures the endpoint reported. On failure it raises `RunnerError`. The message is
saved as-is, so it must not contain secrets. Runners are responsible for their own deadline and
must handle cancellation.

Register a factory before calling `run_config`:

```python
from agent_eval.runners import register_runner

register_runner("my-runner", lambda options, *, task_path: MyRunner(options))
```

The factory receives the model's `options` dict unvalidated. It is called once per attempt
before anything runs, so bad options fail the whole run up front. The registry is per-process.
The `agent-eval` CLI has only the four built-in runners.

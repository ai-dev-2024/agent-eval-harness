# Contributing

## Setup and checks

```sh
make install                  # Python 3.11+; creates .venv with the dev extras
make lint typecheck test      # ruff check + format check, mypy --strict, pytest
make demo                     # offline end-to-end run
```

CI runs the same checks on Python 3.11 and 3.12. Pull requests should pass all of them.

## Code

- Keep runtime dependencies to the current four (pydantic, PyYAML, httpx, jinja2) unless
  there is a strong reason to add one.
- `mypy --strict` covers `src/` and `tests/`.
- Behaviour changes need tests, including the failure path. Coverage is measured with branches
  and must stay at or above 85% (`pyproject.toml`).
- Tests must not touch the network. Use `httpx.MockTransport` for HTTP runners and the `mock`
  runner or a registered fake for engine tests.
- Never save response bodies, request URLs or headers from HTTP errors. They can contain
  credentials.

## Tasks

A new task needs a precise prompt, an independent `reference.py`, and hidden pytest files. See
[docs/reference.md](docs/reference.md#writing-a-task). Before submitting:

- `agent-eval validate-task tasks/<id>/task.yaml` passes;
- the tests cover invalid input and exact boundaries, and include at least one case that a
  plausible but incomplete solution fails;
- every behaviour the tests check is stated in the prompt.

## Pull requests

Describe the problem, the change, and how you verified it. Don't commit `runs/`, `dist/`,
coverage files or anything containing credentials. Report security issues as described in
[SECURITY.md](SECURITY.md), not in a public issue.

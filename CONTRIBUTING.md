# Contributing

Use Python 3.11 or later. Run `make install`, then `make lint typecheck test`.
Run `make demo` for an offline end-to-end check. No API credentials are needed.

Keep runtime dependencies small and annotate public and internal functions. Add focused tests
for behavior changes, including failures and boundary cases. The coverage gate is 85%, with
branches measured. HTTP tests must use `httpx.MockTransport`; never make live model calls in tests.

For a new task, specify behavior precisely, add an independent `reference.py` and hidden pytest
files, and run `agent-eval validate-task path/to/task.yaml`. Include invalid inputs, exact boundaries,
and at least one case that defeats a plausible incomplete solution. Public task fixtures can be
memorized; do not describe their scores as evidence of general coding ability.

Explain the problem, the behavior change, and validation in each proposed change. Keep reports
and credentials out of commits. Discuss security issues privately with the repository maintainer
through the repository's private reporting mechanism if available; do not publish credentials
or a working exploit in a public issue.

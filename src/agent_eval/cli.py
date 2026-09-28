from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import yaml
from pydantic import ValidationError

from agent_eval import __version__
from agent_eval.engine import run_config, validate_task
from agent_eval.report import ReportFormat, render_report
from agent_eval.results import load_attempts, summarize
from agent_eval.specs import discover_tasks


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="agent-eval", description="Compare coding attempts against withheld tests."
    )
    root.add_argument("--version", action="version", version=__version__)
    sub = root.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="execute a run and write results plus an HTML report")
    run.add_argument("config", type=Path)
    run.add_argument("--out", type=Path)
    report = sub.add_parser("report", help="render saved attempts")
    report.add_argument("results", type=Path)
    report.add_argument("--format", choices=["md", "html", "json"], default="md")
    report.add_argument("--out", type=Path)
    report.add_argument("--k", type=int, action="append", help="pass@k to include; repeatable")
    listing = sub.add_parser("list-tasks", help="list matching task specs")
    listing.add_argument("patterns", nargs="*", default=["tasks/*/task.yaml"])
    validate = sub.add_parser("validate-task", help="grade a task's reference implementation")
    validate.add_argument("path", type=Path)
    return root


def describe_error(exc: BaseException) -> str:
    """Name the problem without echoing input values, which can contain secrets."""
    if isinstance(exc, ValidationError):
        problems = [
            f"{'.'.join(str(part) for part in error['loc']) or 'input'}: {error['msg']}"
            for error in exc.errors(include_url=False, include_input=False, include_context=False)
        ]
        message = f"invalid {exc.title}: " + "; ".join(problems[:5])
        if len(problems) > 5:
            message += f"; and {len(problems) - 5} more"
    elif isinstance(exc, yaml.MarkedYAMLError) and exc.problem_mark is not None:
        mark = exc.problem_mark
        message = f"invalid YAML at line {mark.line + 1}, column {mark.column + 1}: {exc.problem}"
    elif isinstance(exc, OSError):
        message = f"{exc.strerror or type(exc).__name__}"
        if exc.filename is not None:
            message += f": {exc.filename}"
    elif isinstance(exc, yaml.YAMLError):
        message = "invalid YAML"
    else:
        message = str(exc) or type(exc).__name__
    return "; ".join([message, *getattr(exc, "__notes__", [])])


def _first_leaf(group: BaseExceptionGroup[BaseException]) -> BaseException:
    first = group.exceptions[0]
    return _first_leaf(first) if isinstance(first, BaseExceptionGroup) else first


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "run":
            out = args.out or Path("runs") / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
            attempts = asyncio.run(run_config(args.config, out))
            passed = sum(row.outcome == "pass" for row in attempts)
            print(
                f"Completed {len(attempts)} attempts; {passed} passed. "
                f"Report: {out / 'report.html'}"
            )
        elif args.command == "report":
            summary = summarize(load_attempts(args.results), tuple(args.k or (1, 2, 5, 10)))
            report = render_report(summary, cast(ReportFormat, args.format))
            if args.out:
                args.out.write_text(report, encoding="utf-8")
            else:
                print(report, end="")
        elif args.command == "list-tasks":
            for path, task in discover_tasks(args.patterns, Path.cwd()):
                print(f"{task.id}\t{task.title}\t{path}")
        else:
            result = asyncio.run(validate_task(args.path))
            print(f"{result.outcome}: {result.passed}/{result.total} tests passed")
            if result.outcome != "pass":
                print(result.log, file=sys.stderr)
                return 1
        return 0
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"agent-eval: {describe_error(exc)}", file=sys.stderr)
        return 2
    except ExceptionGroup as group:
        # Raised when an attempt fails outside its own error handling, e.g. a full disk.
        leaf = _first_leaf(group)
        if not isinstance(leaf, (OSError, ValueError, yaml.YAMLError)):
            raise
        print(f"agent-eval: {describe_error(leaf)}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print(
            "agent-eval: interrupted; completed attempts remain in results.jsonl", file=sys.stderr
        )
        return 130

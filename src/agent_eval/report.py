from __future__ import annotations

from importlib.resources import files
from typing import Literal

from jinja2 import Environment, StrictUndefined, select_autoescape

from agent_eval.results import Summary, summary_json

ReportFormat = Literal["md", "html", "json"]


def _md(value: str) -> str:
    import html

    return html.escape(value).replace("|", "&#124;").replace("\n", " ").replace("\r", " ")


def render_report(summary: Summary, format: ReportFormat) -> str:
    if format == "json":
        return summary_json(summary)
    if format == "md":
        lines = [
            "# Coding task comparison",
            "",
            f"{summary.attempts} attempts. Pass rates are task-macro-averaged. "
            "Missing usage is unknown.",
            "",
            "| Model | Pass@1 | Pass@k | Mean (s) | Median (s) | "
            "Input / output tokens | Cost (USD) |",
            "| --- | ---: | --- | ---: | ---: | --- | --- |",
        ]
        for model in summary.models:
            estimates = ", ".join(f"{k}: {v:.1%}" for k, v in model.pass_at_k.items())
            usage = f"{model.input_tokens} / {model.output_tokens}"
            lines.append(
                f"| {_md(model.model)} | {model.pass_at_1:.1%} | {estimates} | "
                f"{model.mean_wall_time_s:.3f} | {model.median_wall_time_s:.3f} | "
                f"{usage.replace('None', 'unknown')} | "
                f"{model.cost_usd if model.cost_usd is not None else 'unknown'} |"
            )
        lines.extend(["", "## Per-task passes / attempts", ""])
        lines.append("| Task | " + " | ".join(_md(m.model) for m in summary.models) + " |")
        lines.append("| --- | " + " | ".join("---:" for _ in summary.models) + " |")
        for task in summary.task_ids:
            cells = []
            for model in summary.models:
                score = next((s for s in model.tasks if s.task_id == task), None)
                cells.append(f"{score.passed}/{score.attempts}" if score else "—")
            lines.append(f"| {_md(task)} | " + " | ".join(cells) + " |")
        lines.extend(
            [
                "",
                "Reported totals may be partial. Usage coverage (attempts with input/output/cost):",
                "",
            ]
        )
        for model in summary.models:
            lines.append(
                f"- {_md(model.model)}: {model.input_tokens_reported}/"
                f"{model.output_tokens_reported}/{model.cost_reported} of {model.attempts}."
            )
        return "\n".join(lines) + "\n"
    if format != "html":
        raise ValueError(f"unsupported report format: {format}")
    environment = Environment(autoescape=select_autoescape(default=True), undefined=StrictUndefined)
    template = files("agent_eval").joinpath("templates/report.html").read_text(encoding="utf-8")
    max_time = max(t for m in summary.models for t in m.wall_times_s) or 1
    return environment.from_string(template).render(summary=summary, max_time=max_time)

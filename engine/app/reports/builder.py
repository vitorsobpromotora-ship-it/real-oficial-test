"""Geração dos relatórios: JSON (via metrics) e HTML autossuficiente (Jinja2)."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import metrics

_env = Environment(
    loader=FileSystemLoader(Path(__file__).resolve().parent / "templates"),
    autoescape=select_autoescape(["html"]),
)


def source_report_json(source_id: str) -> dict:
    return metrics.source_report(source_id)


def source_report_html(source_id: str) -> str:
    report = metrics.source_report(source_id)
    return _env.get_template("report.html.j2").render(r=report)


def project_report_json(project_id: str) -> dict:
    return metrics.project_report(project_id)

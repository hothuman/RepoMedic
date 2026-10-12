"""Standalone offline HTML report with escaped untrusted project strings."""
from __future__ import annotations

from html import escape
from diagnostics import Report
from version import __version__


def render_html_report(report: Report) -> str:
    counts = report.counts()
    cards = "".join(
        f'<div class="metric"><span>{label}</span><b>{value}</b></div>'
        for label, value in (("Оценка", str(report.score()) + "/100"),
                             ("Ошибки", counts["ERROR"]), ("Предупреждения", counts["WARN"]),
                             ("Успешно", counts["OK"]))
    )
    rows = []
    for finding in report.findings:
        level = finding.level if finding.level in ("OK", "WARN", "ERROR", "INFO", "SKIP") else "INFO"
        advice = (f'<p class="advice">Совет: {escape(finding.advice)}</p>'
                  if finding.advice else "")
        rows.append(f'<article class="finding"><span class="pill {level}">{level}</span>'
                    f'<div><small>{escape(finding.section)}</small>'
                    f'<p>{escape(finding.message)}</p>{advice}</div></article>')
    return """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>RepoMedic — отчёт</title><style>
:root{color-scheme:dark;font-family:system-ui,-apple-system,'Segoe UI',sans-serif;background:#0c1422;color:#e8edf7}
*{box-sizing:border-box}body{max-width:1050px;margin:auto;padding:35px 22px}header{margin-bottom:25px}
h1{font-size:35px;margin:0 0 9px}h1 strong{color:#e63848} .muted{color:#9eadc6;font-size:14px}
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(135px,1fr));gap:12px;margin:22px 0}
.metric,.finding{background:#172234;border:1px solid #2a3b55;border-radius:13px;padding:18px}
.metric span{display:block;color:#a9b7cc;font-size:12px}.metric b{display:block;margin-top:8px;font-size:26px}
.finding{display:flex;gap:14px;margin:10px 0;align-items:flex-start}.finding small{color:#b0c2dd}
.finding p{margin:6px 0;overflow-wrap:anywhere}.advice{color:#a8c8ff;font-size:13px}
.pill{font-size:11px;border-radius:6px;padding:5px 8px;min-width:56px;text-align:center;font-weight:700}
.OK{background:#173c30;color:#85ebbb}.WARN{background:#483521;color:#ffcf85}
.ERROR{background:#4a2730;color:#ff9fab}.INFO,.SKIP{background:#293852;color:#abc8ff}
.path{overflow-wrap:anywhere;font-family:ui-monospace,monospace}footer{padding:22px 0;color:#90a5c0;font-size:12px}
</style></head><body><header><h1><strong>✚</strong> RepoMedic</h1>
<p class="muted">Версия """ + escape(__version__) + """ · Статический анализ, без выполнения кода · Не является аудитом безопасности</p>
<p class="path">""" + escape(str(report.folder)) + """</p>
<p class="muted">Источник: """ + ("GitHub ZIP" if report.source == "github" else "Локальная папка") + """</p>
</header><div class="metrics">""" + cards + """</div><h2>Результаты проверки</h2>""" + "".join(rows) + """
<footer>Оценка: 100 − 18 × ошибки − 7 × предупреждения (минимум 0). Программа не запускала код проекта.</footer>
</body></html>"""

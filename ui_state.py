"""Small, bounded, local-only settings and scan history for RepoMedic v0.9.

No tracking, telemetry, network I/O, or background uploads.
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from diagnostics import Finding, Report
from report_io import atomic_save_text

MAX_HISTORY = 50
MAX_FINDINGS = 800
MAX_STORAGE_BYTES = 2_000_000


def default_storage_dir() -> Path:
    """Per-user writable location on Windows, Linux and macOS."""
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "RepoMedic"
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "repomedic"


def _read_json(path: Path, fallback: Any) -> Any:
    try:
        if not path.is_file() or path.stat().st_size > MAX_STORAGE_BYTES:
            return fallback
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return fallback


def load_settings(storage_dir: Path) -> dict[str, Any]:
    defaults = {"theme": "dark", "save_history": True, "language": "en"}
    saved = _read_json(storage_dir / "settings.json", {})
    if isinstance(saved, dict):
        if saved.get("theme") in ("dark", "light"):
            defaults["theme"] = saved["theme"]
        if saved.get("language") in ("en", "ru"):
            defaults["language"] = saved["language"]
        if type(saved.get("save_history")) is bool:
            defaults["save_history"] = saved["save_history"]
    return defaults


def save_settings(storage_dir: Path, settings: dict[str, Any]) -> None:
    cleaned = {
        "theme": settings.get("theme") if settings.get("theme") in ("light", "dark") else "dark",
        "save_history": settings.get("save_history") is not False,
        "language": settings.get("language") if settings.get("language") in ("en", "ru") else "en",
    }
    storage_dir.mkdir(parents=True, exist_ok=True)
    atomic_save_text(storage_dir / "settings.json", json.dumps(cleaned, ensure_ascii=False, indent=2))


def load_history(storage_dir: Path) -> list[dict[str, Any]]:
    saved = _read_json(storage_dir / "history.json", [])
    if not isinstance(saved, list):
        return []
    validated: list[dict[str, Any]] = []
    for item in saved[:MAX_HISTORY]:
        if not (isinstance(item, dict) and isinstance(item.get("folder"), str)
                and isinstance(item.get("findings"), list)
                and isinstance(item.get("counts"), dict)):
            continue
        duration = item.get("duration_seconds")
        if type(duration) not in (int, float) or not math.isfinite(duration) or duration < 0:
            continue
        if not isinstance(item.get("date_utc"), str) or not isinstance(item.get("label"), str):
            continue
        validated.append({**item, "label": item["label"][:150],
                          "folder": item["folder"][:1500],
                          "findings": [f for f in item["findings"][:MAX_FINDINGS] if isinstance(f, dict)]})
    return validated


def save_history(storage_dir: Path, history: list[dict[str, Any]]) -> None:
    storage_dir.mkdir(parents=True, exist_ok=True)
    content = json.dumps(history[:MAX_HISTORY], ensure_ascii=False, indent=2)
    # A single scan of a huge project must not exhaust the history store.
    if len(content.encode("utf-8")) > MAX_STORAGE_BYTES:
        history = history[:10]
        content = json.dumps(history, ensure_ascii=False, separators=(",", ":"))
    if len(content.encode("utf-8")) > MAX_STORAGE_BYTES:
        raise ValueError("История слишком большая; отключите её сохранение в настройках")
    atomic_save_text(storage_dir / "history.json", content)


def snapshot(report: Report, duration_seconds: float, label: str = "") -> dict[str, Any]:
    # Limit each field to prevent enormous / malformed repositories filling local storage.
    counts = report.counts()
    return {
        "date_utc": datetime.now(timezone.utc).isoformat(),
        "folder": str(report.folder)[:1500],
        "label": (label or report.folder.name)[:150],
        "source": report.source,
        "score": report.score(),
        "counts": counts,
        "duration_seconds": round(max(0.0, duration_seconds), 3),
        "findings": [
            {"level": f.level[:12], "section": f.section[:150],
             "message": f.message[:2000], "advice": f.advice[:1500] if f.advice else None}
            for f in report.findings[:MAX_FINDINGS]
        ],
        "truncated": len(report.findings) > MAX_FINDINGS,
    }


def restore_report(item: dict[str, Any]) -> Report:
    report = Report(folder=Path(item["folder"]),
                    source=item.get("source", "local") if item.get("source") in ("local", "github") else "local")
    for raw in item.get("findings", [])[:MAX_FINDINGS]:
        if not isinstance(raw, dict):
            continue
        report.findings.append(Finding(
            level=str(raw.get("level", "INFO")),
            section=str(raw.get("section", "")),
            message=str(raw.get("message", "")),
            advice=str(raw["advice"]) if isinstance(raw.get("advice"), str) else None,
        ))
    return report


def add_to_history(history: list[dict[str, Any]], entry: dict[str, Any]) -> list[dict[str, Any]]:
    return [entry, *history][:MAX_HISTORY]


def clear_history(storage_dir: Path) -> None:
    # Intentionally remove all saved scan records; never touches project folders.
    (storage_dir / "history.json").unlink(missing_ok=True)

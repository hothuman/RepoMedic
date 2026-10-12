"""Lightweight project hygiene hints. No source code or secrets are read."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from diagnostics import Report


def _ignored(patterns: set[str], target: str) -> bool:
    """Conservative common-pattern recognition; not a complete gitignore engine."""
    if target == ".env":
        return any(p in patterns for p in (".env", "/.env", ".env*", ".env.*", "**/.env", "**/.env*"))
    return target in patterns or "/" + target in patterns or target + "/" in patterns or "/" + target + "/" in patterns


def analyze_project_hygiene(root: Path, report: Report, *, has_python: bool, has_node: bool) -> None:
    section = "Гигиена проекта"
    ignored: set[str] = set()
    ignore = root / ".gitignore"
    if ignore.is_file() and ignore.resolve().is_relative_to(root.resolve()):
        try:
            if ignore.stat().st_size <= 512 * 1024:
                ignored = {line.strip() for line in ignore.read_text(encoding="utf-8-sig").splitlines()
                           if line.strip() and not line.lstrip().startswith("#") and not line.lstrip().startswith("!")}
            else:
                report.add("SKIP", section, "Очень большой .gitignore: правила не анализировались")
        except (OSError, UnicodeError):
            report.add("SKIP", section, "Не удалось прочитать правила .gitignore")

    # Important: never read .env or show its values. A missing rule is a possible
    # privacy problem, but actual Git tracking status is NOT established here.
    env_file = root / ".env"
    if env_file.is_file() and not _ignored(ignored, ".env"):
        report.add("WARN", section, "В корне есть .env, но простое правило исключения не найдено в .gitignore",
                   "Проверьте правила Git и выполните 'git ls-files .env' вручную. Не публикуйте реальные секреты.")
    elif env_file.is_file():
        report.add("OK", section, "Для .env найдено подходящее простое правило .gitignore (отслеживание Git не проверялось)")

    if (root / ".git").exists():
        if has_python and (root / ".venv").is_dir() and not _ignored(ignored, ".venv"):
            report.add("WARN", section, ".venv присутствует, но простое правило исключения не обнаружено",
                       "Добавьте .venv/ в .gitignore и проверьте, не отслеживается ли папка Git.")
        if has_node and (root / "node_modules").is_dir() and not _ignored(ignored, "node_modules"):
            report.add("WARN", section, "node_modules присутствует, но простое правило исключения не обнаружено",
                       "Добавьте node_modules/ в .gitignore и проверьте индекс Git.")

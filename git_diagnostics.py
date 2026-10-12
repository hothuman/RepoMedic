"""Offline, read-only local Git metadata inspection. Never invokes git."""
from __future__ import annotations

import configparser
import re
from pathlib import Path
from urllib.parse import urlsplit
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from diagnostics import Report

GITHUB_SSH = re.compile(r"^git@github\.com:([a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+?)(?:\.git)?$")


def _public_remote(raw: str) -> tuple[str, bool]:
    """Return a non-sensitive remote description, never leak embedded tokens."""
    raw = raw.strip()
    match = GITHUB_SSH.fullmatch(raw)
    if match:
        return f"GitHub: {match.group(1)}", True
    try:
        parts = urlsplit(raw)
    except ValueError:
        return "Удалённый репозиторий настроен (URL скрыт)", False
    if parts.scheme in ("http", "https", "ssh") and parts.hostname:
        hostname = parts.hostname.lower()
        if hostname == "github.com":
            repo = parts.path.strip("/")
            if re.fullmatch(r"[\w.-]+/[\w.-]+(?:\.git)?", repo):
                return "GitHub: " + repo.removesuffix(".git"), True
        return f"Удалённый сервер: {hostname}", False
    return "Удалённый репозиторий настроен (URL скрыт)", False


def analyze_git(root: Path, report: Report) -> None:
    entry = root / ".git"
    if entry.is_symlink() and not entry.resolve().is_relative_to(root.resolve()):
        report.add("WARN", "Git", "Внешняя символическая ссылка .git не анализируется")
        return
    if not entry.exists():
        report.add("INFO", "Git", "Git-метаданные отсутствуют (возможно, скачан ZIP)")
        return
    if entry.is_file():
        report.add("INFO", "Git", "Обнаружена ссылка на Git worktree/submodule; внешние пути не читаются")
        return
    if not entry.is_dir():
        report.add("WARN", "Git", "Неизвестный формат .git")
        return
    report.add("OK", "Git", "Найден локальный Git-репозиторий")
    head = entry / "HEAD"
    try:
        if head.is_file() and head.resolve().is_relative_to(entry.resolve()) and head.stat().st_size < 4096:
            value = head.read_text(encoding="utf-8", errors="replace").strip()
            if value.startswith("ref: refs/heads/"):
                report.add("INFO", "Git", f"Ветка: {value.removeprefix('ref: refs/heads/')[:100]}")
            elif re.fullmatch(r"[0-9a-fA-F]{40,64}", value):
                report.add("INFO", "Git", "Detached HEAD")
    except OSError:
        report.add("WARN", "Git", "Не удалось прочитать HEAD")
    config = entry / "config"
    try:
        if not config.is_file() or not config.resolve().is_relative_to(entry.resolve()) or config.stat().st_size > 1024 * 1024:
            report.add("INFO", "Git", "Конфигурация Git отсутствует или слишком большая")
            return
        parser = configparser.ConfigParser(interpolation=None, strict=False)
        parser.read(config, encoding="utf-8")
        if parser.has_option('remote "origin"', "url"):
            desc, is_github = _public_remote(parser.get('remote "origin"', "url"))
            report.add("OK" if is_github else "INFO", "Git", f"Origin: {desc}")
        else:
            report.add("INFO", "Git", "Remote origin не настроен")
    except (OSError, configparser.Error, UnicodeError):
        report.add("WARN", "Git", "Не удалось прочитать .git/config")

"""Bounded, read-only checks of Python source syntax and declared dependencies.

The selected project's Python files are parsed as text, NEVER imported, compiled
into executable artifacts, or executed.  Parsing uses the running interpreter's
syntax rules, which may not match the project's target Python version.
"""

from __future__ import annotations

import ast
import os
import tokenize
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

if TYPE_CHECKING:
    from diagnostics import Report

SKIP_DIRS = {
    ".git", ".venv", "venv", "env", "node_modules", "__pycache__", ".tox",
    ".nox", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".idea",
    "build", "dist", ".next", "site-packages", ".eggs", ".hg", ".svn",
}
MAX_FILES = 400
MAX_BYTES_PER_FILE = 512 * 1024
MAX_TOTAL_BYTES = 12 * 1024 * 1024
MAX_WALK_DIRS = 2000


def check_python_syntax(root: Path, report: Report) -> None:
    """Recursively check a bounded set of .py files, excluding generated folders.

    Symlink files/directories are skipped even when linking inside the project;
    os.walk never follows directory symlinks. Only a relative filename and a
    standard parser diagnostic are emitted, not source code snippets.
    """
    section = "Синтаксис Python"
    scanned = 0
    skipped = 0
    errors = 0
    read_bytes = 0
    walked = 0
    truncated = False
    root = root.resolve()

    for base, folders, filenames in os.walk(root, followlinks=False):
        walked += 1
        if walked > MAX_WALK_DIRS:
            truncated = True
            break
        base_path = Path(base)
        folders[:] = sorted(d for d in folders if d not in SKIP_DIRS and
                            not (base_path / d).is_symlink())
        for filename in sorted(filenames):
            if not filename.endswith(".py"):
                continue
            path = base_path / filename
            if path.is_symlink():
                skipped += 1
                continue
            if scanned >= MAX_FILES or read_bytes >= MAX_TOTAL_BYTES:
                truncated = True
                break
            try:
                stat = path.stat()
                if stat.st_size > MAX_BYTES_PER_FILE or read_bytes + stat.st_size > MAX_TOTAL_BYTES:
                    skipped += 1
                    continue
                # A path with no symlinked parents is ensured by os.walk's prune.
                if not path.resolve().is_relative_to(root):
                    skipped += 1
                    continue
                scanned += 1
                read_bytes += stat.st_size
                with tokenize.open(path) as stream:
                    content = stream.read()
                ast.parse(content, filename=path.relative_to(root).as_posix())
            except (SyntaxError, UnicodeError, ValueError) as exc:
                errors += 1
                # Avoid reflecting source excerpts or an untrusted file content.
                msg = exc.msg if isinstance(exc, SyntaxError) else type(exc).__name__
                line = getattr(exc, "lineno", None)
                loc = f", строка {line}" if line is not None else ""
                report.add("ERROR", section, f"{path.relative_to(root).as_posix()}{loc}: {msg}",
                           "Исправьте синтаксис файла; учтите версию Python, на которой работает RepoMedic.")
            except OSError as exc:
                skipped += 1
                report.add("SKIP", section,
                           f"Не удалось прочитать {path.relative_to(root).as_posix()}: {type(exc).__name__}")
        if truncated:
            break

    if scanned:
        report.add("OK" if errors == 0 else "INFO", section,
                   f"Проверено Python-файлов: {scanned}; синтаксических ошибок: {errors}")
    else:
        report.add("SKIP", section, "Файлы .py для статической проверки синтаксиса не найдены")
    if skipped:
        report.add("SKIP", section, f"Пропущено файлов (лимиты, ссылки или чтение): {skipped}")
    if truncated:
        report.add("WARN", section,
                   f"Достигнут предел обхода ({MAX_FILES} файлов, {MAX_WALK_DIRS} каталогов, {MAX_TOTAL_BYTES // 1048576} МиБ)",
                   "Выберите более узкую папку проекта для полной диагностики.")
    report.add("INFO", section,
               "Проверка использует грамматику Python, запускающего RepoMedic; несовпадение версий может повлиять на результат")


def check_dependency_conflicts(requirements: list[Requirement], report: Report) -> None:
    """Detect contradictory exact pins among unconditional PEP 508 requirements.

    Deliberately conservative: does not claim to solve arbitrary constraint
    intersections, ignores conditional requirements and URL requirements, and
    never requests an installation or imports project packages.
    """
    grouped: dict[str, list[Requirement]] = defaultdict(list)
    for req in requirements:
        if req.marker is not None or req.url is not None:
            continue
        grouped[canonicalize_name(req.name)].append(req)

    issues = 0
    for name, reqs in sorted(grouped.items()):
        if len(reqs) < 2:
            continue
        exact: dict[str, Version] = {}
        for req in reqs:
            for item in req.specifier:
                if item.operator != "==" or "*" in item.version:
                    continue
                try:
                    ver = Version(item.version)
                except InvalidVersion:
                    continue
                exact[str(ver)] = ver
        if not exact:
            continue
        if len(exact) > 1 or any(
            ver not in req.specifier for ver in exact.values() for req in reqs
        ):
            issues += 1
            distinct = sorted({str(r.specifier) or "без ограничений" for r in reqs})
            report.add("ERROR", "Конфликты зависимостей",
                       f"{name}: несовместимые объявленные ограничения: {', '.join(distinct)[:200]}",
                       "Согласуйте версии в requirements.txt и pyproject.toml; проверьте маркеры окружения.")
    if not issues:
        report.add("OK", "Конфликты зависимостей", "Противоречащих безусловных точных версий не выявлено")
    report.add("INFO", "Конфликты зависимостей",
               "Проверяются только конфликты с точными ==версиями без маркеров; это не полный dependency solver")

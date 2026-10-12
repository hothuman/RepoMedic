"""Read-only lightweight GitHub repository readiness and Actions hygiene checks.

This only evaluates files in a local checkout or public ZIP. It cannot inspect
GitHub settings, permissions, branch protection or remote security status.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from diagnostics import Report

MAX_WORKFLOWS = 24
MAX_SIZE = 512 * 1024
_SHA_REF = re.compile(r"^[0-9a-fA-F]{40}$")
_USES = re.compile(r"\buses\s*:\s*['\"]?([^\s#'\"]+)")


def _exists(root: Path, name: str) -> bool:
    path = root / name
    return path.is_file() and not path.is_symlink()


def analyze_github_readiness(root: Path, report: Report, *, has_python: bool, has_node: bool) -> None:
    section = "GitHub: готовность"
    has_github = (root / ".github").is_dir()
    if report.source != "github" and not has_github and not (root / ".git").exists():
        report.add("INFO", section, "Нет явных признаков GitHub; проверены только локальные файлы")
    if _exists(root, "README.md"):
        report.add("OK", section, "README.md найден")
    else:
        report.add("WARN", section, "README.md отсутствует", "Добавьте инструкцию установки, запуска и примеры использования.")
    if _exists(root, "LICENSE") or _exists(root, "LICENSE.md") or _exists(root, "LICENSE.txt"):
        report.add("OK", section, "Файл лицензии найден")
    else:
        report.add("WARN", section, "Лицензия отсутствует", "Укажите условия распространения кода (например, MIT) в LICENSE.")
    if any(_exists(root, name) for name in ("SECURITY.md", ".github/SECURITY.md", "docs/SECURITY.md")):
        report.add("OK", section, "Политика сообщения об уязвимостях найдена")
    else:
        report.add("INFO", section, "SECURITY.md не найден (рекомендован для публичных проектов)",
                   "Добавьте способ приватно сообщить о возможной уязвимости.")
    if any(_exists(root, name) for name in ("CONTRIBUTING.md", ".github/CONTRIBUTING.md")):
        report.add("OK", section, "Инструкция для участников найдена")
    else:
        report.add("INFO", section, "CONTRIBUTING.md не найден", "Опишите правила внесения изменений и проверки тестов.")
    if any(_exists(root, name) for name in (".github/dependabot.yml", ".github/dependabot.yaml")):
        report.add("OK", section, "Dependabot-конфигурация присутствует (содержимое не проверялось)")
    elif has_python or has_node:
        report.add("INFO", section, "Dependabot-конфигурация отсутствует", "Можно настроить регулярные обновления зависимостей.")

    workflow_dir = root / ".github" / "workflows"
    if not workflow_dir.is_dir() or workflow_dir.is_symlink():
        report.add("INFO", section, "GitHub Actions workflows не найдены", "При необходимости добавьте CI для автоматических тестов.")
        return
    try:
        paths = sorted((p for p in workflow_dir.iterdir() if p.suffix.lower() in (".yml", ".yaml") and p.is_file()), key=lambda p: p.name)
    except OSError:
        report.add("SKIP", section, "Не удалось прочитать .github/workflows")
        return
    if not paths:
        report.add("INFO", section, "Файлы workflow не найдены")
        return
    report.add("OK", section, f"Файлов GitHub Actions workflow: {len(paths)}")
    if len(paths) > MAX_WORKFLOWS:
        report.add("SKIP", section, f"Проверены только первые {MAX_WORKFLOWS} workflows")
    warning_limit = 12
    emitted = 0
    for path in paths[:MAX_WORKFLOWS]:
        try:
            if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()) or path.stat().st_size > MAX_SIZE:
                report.add("SKIP", section, f"{path.name}: ссылка или слишком большой файл")
                continue
            data = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError, ValueError):
            report.add("SKIP", section, f"{path.name}: не удалось прочитать workflow")
            continue
        issues: list[tuple[str, str]] = []
        for number, line in enumerate(data.splitlines()[:2500], 1):
            clean = line.strip()
            if clean.startswith("#"):
                continue
            match = _USES.search(clean)
            if match:
                used = match.group(1)
                if used.startswith("./") or used.startswith("docker://") or "${{" in used:
                    continue
                reference = used.rpartition("@")[2]
                if not reference:
                    issues.append((f"{path.name}:{number}: action без закреплённой версии", "Укажите проверенный commit SHA для стороннего action."))
                elif not _SHA_REF.fullmatch(reference):
                    issues.append((f"{path.name}:{number}: action привязан к изменяемому тегу", "Для повышенной защиты закрепите action на полный 40-символьный commit SHA."))
            if re.match(r"^permissions\s*:\s*write-all(?:\s*#.*)?$", clean):
                issues.append((f"{path.name}:{number}: permissions: write-all", "Выдавайте только необходимые permissions конкретным jobs."))
            if re.search(r"\b(?:curl|wget)\b[^\n|]*\|\s*(?:sh|bash)\b", clean, re.I):
                issues.append((f"{path.name}:{number}: выполнение скачанного shell-скрипта", "Проверьте источник, содержимое и версию запускаемого скрипта."))
        if re.search(r"\bpull_request_target\s*:", data) and re.search(r"\bactions/checkout@", data):
            issues.append((f"{path.name}: сочетание pull_request_target и checkout требует ручной проверки",
                           "Убедитесь, что недоверенный код PR не запускается с привилегированным токеном."))
        for issue, advice in issues[:max(0, warning_limit - emitted)]:
            report.add("WARN", "GitHub Actions", issue, advice)
            emitted += 1
        if emitted >= warning_limit:
            report.add("SKIP", "GitHub Actions", "Ограничено количество предупреждений о workflows (12)")
            break
    report.add("INFO", section, "GitHub Actions анализируются текстово: настройки GitHub и реальное выполнение не проверяются")

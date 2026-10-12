"""Bounded read-only Dockerfile and Compose checks; never executes Docker.

This is intentionally conservative static linting, not a Docker parser, image
scanner, vulnerability assessment or a secret scanner. No values of ENV/ARG are
shown in reports.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from diagnostics import Report

MAX_BYTES = 1024 * 1024
MAX_LINES = 2500
MAX_FILES = 16
_SECRET = re.compile(r"(?:PASS(?:WORD)?|TOKEN|SECRET|API[_-]?KEY|PRIVATE[_-]?KEY|CREDENTIAL|AUTH)", re.I)
_DOCKERFILE = re.compile(r"^Dockerfile(?:\.[a-zA-Z0-9_.-]+)?$")
_IMAGE = re.compile(r"^([\w./:-]+)(?:\s+AS\s+[\w-]+)?$", re.I)


def _display_path(path: Path, root: Path) -> str:
    """Display project-relative paths consistently on Windows and Linux."""
    return path.relative_to(root).as_posix()


def _read(path: Path, root: Path, report: Report, section: str) -> list[str] | None:
    try:
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            report.add("SKIP", section, f"{_display_path(path, root)}: символическая ссылка не читается")
            return None
        if path.stat().st_size > MAX_BYTES:
            report.add("SKIP", section, f"{_display_path(path, root)}: более 1 МиБ, проверка пропущена")
            return None
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        if len(lines) > MAX_LINES:
            report.add("SKIP", section, f"{_display_path(path, root)}: более {MAX_LINES} строк, проверка пропущена")
            return None
        return lines
    except (OSError, UnicodeError, ValueError) as exc:
        report.add("SKIP", section, f"Не удалось прочитать {path.name}: {type(exc).__name__}")
        return None


def _instructions(lines: list[str]):
    """Join continuations and return (line_number, keyword, body)."""
    buffer = ""
    start = 0
    for number, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if not buffer:
            start = number
        buffer += (" " if buffer else "") + line.rstrip("\\").strip()
        if line.endswith("\\"):
            continue
        match = re.match(r"^([A-Za-z]+)\s+(.*)$", buffer, re.S)
        if match:
            yield start, match.group(1).upper(), match.group(2).strip()
        buffer = ""
    if buffer:
        match = re.match(r"^([A-Za-z]+)\s+(.*)$", buffer, re.S)
        if match:
            yield start, match.group(1).upper(), match.group(2).strip()


def _dockerfile(path: Path, root: Path, report: Report) -> None:
    section = "Dockerfile"
    lines = _read(path, root, report, section)
    if lines is None:
        return
    name = _display_path(path, root)
    instructions = list(_instructions(lines))
    froms = [(n, text) for n, cmd, text in instructions if cmd == "FROM"]
    if not froms:
        report.add("ERROR", section, f"{name}: нет инструкции FROM", "Добавьте базовый образ: FROM python:3.13-slim (с подходящим тегом или digest).")
        return
    aliases = set()
    for number, command, body in instructions:
        if command == "FROM":
            image = re.sub(r"^--platform=\S+\s+", "", body).split()[0] if body.split() else ""
            match = re.search(r"\s+AS\s+(\S+)", body, re.I)
            if match:
                aliases.add(match.group(1).lower())
            if not image or "$" in image or image.lower() in aliases or image.isdigit():
                continue
            if image.endswith(":latest") or (":" not in image.rsplit("/", 1)[-1] and "@sha256:" not in image):
                report.add("WARN", section, f"{name}:{number}: образ без фиксированной версии ({image[:100]})",
                           "Укажите осмысленный тег версии или digest; latest ухудшает воспроизводимость.")
        elif command in ("ARG", "ENV"):
            left = body.split("=", 1)[0].split()[0] if body.split() else ""
            if _SECRET.search(left) and ("=" in body or command == "ENV"):
                report.add("WARN", section, f"{name}:{number}: возможный секрет в {command} ({left[:60]})",
                           "Не передавайте секреты через ARG/ENV в образ; используйте runtime secrets или BuildKit secret mounts.")
        elif command == "ADD" and re.search(r"https?://", body, re.I):
            report.add("WARN", section, f"{name}:{number}: ADD загружает URL",
                       "Проверяйте источник и контрольную сумму; используйте воспроизводимую загрузку.")
        elif command == "RUN" and re.search(r"(?:curl|wget)\b[^\n|]*\|\s*(?:sh|bash)\b", body, re.I):
            report.add("WARN", section, f"{name}:{number}: загрузка скрипта напрямую в shell",
                       "Не исполняйте удалённый скрипт без проверки; закрепите версию и проверьте целостность.")
    stages = []
    for _, cmd, body in instructions:
        if cmd == "FROM":
            stages.append([])
        elif stages:
            stages[-1].append((cmd, body))
    if stages:
        last = stages[-1]
        users = [text for cmd, text in last if cmd == "USER"]
        if not users:
            report.add("WARN", section, f"{name}: в финальном этапе не задан USER",
                       "Если приложение позволяет, запускайте контейнер от непривилегированного пользователя.")
        elif users[-1].strip().lower() in ("root", "0", "0:0", "root:root"):
            report.add("WARN", section, f"{name}: финальный этап запускается от root",
                       "Создайте отдельного пользователя и переключитесь на него через USER.")
    if any(cmd in ("COPY", "ADD") and re.search(r"(?:^|\s)\.\s+(?:\.|/|\S+)", body) for _, cmd, body in instructions):
        if not (root / ".dockerignore").is_file() and not (path.parent / ".dockerignore").is_file():
            report.add("WARN", section, f"{name}: COPY/ADD . без .dockerignore",
                       "Добавьте .dockerignore для .git, .env, .venv, node_modules и других ненужных файлов.")
    report.add("OK", section, f"{name}: прочитано инструкций {len(instructions)}, этапов {len(froms)}")


def _compose(path: Path, root: Path, report: Report) -> None:
    """Text checks only; no YAML semantic interpretation or variable expansion."""
    section = "Docker Compose"
    lines = _read(path, root, report, section)
    if lines is None:
        return
    name = _display_path(path, root)
    if not any(re.match(r"^services\s*:\s*(?:#.*)?$", x) for x in lines):
        report.add("WARN", section, f"{name}: не найден блок services:", "Проверьте структуру Compose-файла.")
        return
    service_names: list[str] = []
    inside_services = False
    for number, raw in enumerate(lines, 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        stripped = raw.strip()
        if indent == 0:
            inside_services = bool(re.match(r"services\s*:", stripped))
            continue
        if not inside_services:
            continue
        if indent == 2 and re.match(r"^[\w.-]+\s*:", stripped):
            service_names.append(stripped.split(":", 1)[0][:80])
            if len(service_names) >= 100:
                break
        if re.match(r"^privileged\s*:\s*true(?:\s*(?:#.*)?)?$", stripped, re.I):
            report.add("WARN", section, f"{name}:{number}: privileged: true",
                       "Уберите privileged или ограничьте capabilities; проверьте реальную необходимость.")
        if re.match(r"^network_mode\s*:\s*['\"]?host['\"]?(?:\s*#.*)?$", stripped, re.I):
            report.add("WARN", section, f"{name}:{number}: network_mode: host",
                       "Используйте изолированную сеть, если host networking не требуется.")
        if "docker.sock" in stripped and not stripped.startswith("#"):
            report.add("WARN", section, f"{name}:{number}: упоминание Docker socket",
                       "Монтирование docker.sock предоставляет высокий уровень доступа к Docker-хосту.")
        if re.match(r"^image\s*:\s*\S+(?:\s*#.*)?$", stripped, re.I):
            value = stripped.split(":", 1)[1].split("#", 1)[0].strip().strip("\"'")
            if "$" not in value and (value.endswith(":latest") or (":" not in value.rsplit("/", 1)[-1] and "@sha256:" not in value)):
                report.add("WARN", section, f"{name}:{number}: образ без фиксированной версии ({value[:90]})",
                           "Закрепите тег версии или digest для воспроизводимости.")
    if not service_names:
        report.add("WARN", section, f"{name}: службы не распознаны (поддерживается только простой YAML с отступами)")
    else:
        report.add("OK", section, f"{name}: найдено служб {len(service_names)}; YAML проверен частично")
    report.add("INFO", section, "Статическая проверка Compose: без полноценного YAML-парсера и разрешения переменных")


def analyze_docker(root: Path, report: Report) -> None:
    candidates: list[Path] = []
    try:
        for directory in (root, root / "docker"):
            if not directory.is_dir() or directory.is_symlink():
                continue
            for path in directory.iterdir():
                if path.is_file() and _DOCKERFILE.fullmatch(path.name):
                    candidates.append(path)
        for name in ("compose.yml", "compose.yaml", "docker-compose.yml", "docker-compose.yaml"):
            path = root / name
            if path.is_file():
                candidates.append(path)
    except OSError:
        report.add("SKIP", "Docker", "Не удалось перечислить Docker-файлы")
        return
    if not candidates:
        report.add("INFO", "Docker", "Dockerfile/Compose не обнаружены; проверка пропущена")
        return
    dockerfiles = sorted((p for p in candidates if _DOCKERFILE.fullmatch(p.name)), key=str)
    composefiles = sorted((p for p in candidates if p not in dockerfiles), key=str)
    report.add("INFO", "Docker", f"Найдено конфигураций: {len(candidates)}")
    for path in dockerfiles[:MAX_FILES]:
        _dockerfile(path, root, report)
    for path in composefiles[:MAX_FILES]:
        _compose(path, root, report)
    if len(dockerfiles) > MAX_FILES or len(composefiles) > MAX_FILES:
        report.add("SKIP", "Docker", f"Превышен лимит проверяемых файлов ({MAX_FILES} каждого типа)")

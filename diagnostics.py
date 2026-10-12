"""Read-only static diagnostics for Python, Node.js and local Git projects.

Does not import or execute code from the selected project.
"""

from __future__ import annotations

import importlib.metadata
import json
from dataclasses import asdict
from datetime import datetime, timezone
import re
import tomllib
import time
from dataclasses import dataclass, field
from pathlib import Path

from version import __version__

from packaging.markers import default_environment
from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version


@dataclass(frozen=True)
class Finding:
    level: str
    section: str
    message: str
    advice: str | None = None


@dataclass
class Report:
    folder: Path
    findings: list[Finding] = field(default_factory=list)
    source: str = "local"

    def add(self, level: str, section: str, message: str, advice: str | None = None) -> None:
        self.findings.append(Finding(level, section, message, advice))

    def counts(self) -> dict[str, int]:
        return {name: sum(f.level == name for f in self.findings)
                for name in ("OK", "WARN", "ERROR", "INFO", "SKIP")}

    def score(self) -> int:
        """Transparent heuristic, not a security or quality certification."""
        counts = self.counts()
        return max(0, 100 - 18 * counts["ERROR"] - 7 * counts["WARN"])

    def to_dict(self) -> dict:
        return {
            "tool": "RepoMedic",
            "version": __version__,
            "source": self.source,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "folder": str(self.folder),
            "score": self.score(),
            "score_note": "Эвристика: 100 − 18×ERROR − 7×WARN; не аудит безопасности.",
            "counts": self.counts(),
            "findings": [asdict(f) for f in self.findings],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def to_text(self) -> str:
        counts = self.counts()
        lines = [
            f"REPOMEDIC {__version__}  |  СТАТИЧЕСКАЯ ДИАГНОСТИКА ПРОЕКТА",
            "=" * 63,
            f"Папка: {self.folder}",
            f"Источник: {'GitHub ZIP' if self.source == 'github' else 'Локальный проект'}",
            f"Итог: {counts['ERROR']} ошибок, {counts['WARN']} предупреждений, "
            f"{counts['OK']} успешных проверок",
            f"Health Score: {self.score()}/100 (эвристика, не аудит безопасности)",
        ]
        sections = dict.fromkeys(f.section for f in self.findings)
        for section in sections:
            lines.extend(("", f"--- {section} ---"))
            for item in self.findings:
                if item.section == section:
                    lines.append(f"[{item.level}] {item.message}")
                    if item.advice:
                        lines.append(f"    Совет: {item.advice}")
        lines.extend(("", "Проверка завершена. Код проекта не выполнялся."))
        return "\n".join(lines)


def _load_requirements(root: Path, file: Path, report: Report,
                       visited: set[Path], depth: int = 0) -> list[Requirement]:
    result: list[Requirement] = []
    resolved = file.resolve()
    if not resolved.is_relative_to(root.resolve()):
        report.add("WARN", "Зависимости", f"Пропущена ссылка за пределы проекта: {file}")
        return result
    if resolved in visited:
        report.add("INFO", "Зависимости", f"Повторная ссылка пропущена: {file.name}")
        return result
    if depth > 5:
        report.add("WARN", "Зависимости", "Превышена глубина вложенности -r (5)")
        return result
    visited.add(resolved)
    try:
        if resolved.stat().st_size > 2 * 1024 * 1024:
            report.add("WARN", "Зависимости", f"{file.name}: превышен лимит 2 МиБ для текстового файла")
            return result
        content = resolved.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        report.add("ERROR", "Зависимости", f"Невозможно прочитать {file.name}: {exc}")
        return result

    lines = content.splitlines()
    if len(lines) > 2000:
        report.add("WARN", "Зависимости", f"{file.name}: анализируются только первые 2000 строк")
    for line_no, raw in enumerate(lines[:2000], start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-r ") or line.startswith("--requirement "):
            include = line.split(maxsplit=1)[1].strip()
            if not include or include.startswith("-"):
                report.add("WARN", "Зависимости", f"{file.name}:{line_no}: некорректный -r")
                continue
            result.extend(_load_requirements(root, resolved.parent / include,
                                             report, visited, depth + 1))
            continue
        if line.startswith("-"):
            report.add("WARN", "Зависимости", f"{file.name}:{line_no}: параметр pip не анализируется: {line[:90]}")
            continue
        # pip allows comments after whitespace. URL fragment #egg is left intact.
        line = re.split(r"\s+#", line, maxsplit=1)[0].strip()
        try:
            result.append(Requirement(line))
        except InvalidRequirement:
            report.add("WARN", "Зависимости", f"{file.name}:{line_no}: неподдерживаемая запись: {line[:90]}")
    return result


def _read_pyproject(root: Path, report: Report) -> tuple[list[Requirement], str | None]:
    config_path = root / "pyproject.toml"
    if not config_path.is_file():
        return [], None
    if not config_path.resolve().is_relative_to(root.resolve()):
        report.add("WARN", "Зависимости", "pyproject.toml ссылается за пределы проекта")
        return [], None
    try:
        if config_path.stat().st_size > 2 * 1024 * 1024:
            report.add("WARN", "Зависимости", "pyproject.toml слишком большой (предел 2 МиБ)")
            return [], None
        with config_path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        report.add("ERROR", "Зависимости", f"Невозможно прочитать pyproject.toml: {exc}")
        return [], None
    project = data.get("project", {})
    if not isinstance(project, dict):
        report.add("WARN", "Зависимости", "Некорректная секция [project]")
        return [], None
    if not isinstance(project.get("dynamic", []), list):
        report.add("WARN", "Зависимости", "Некорректное поле project.dynamic")
    elif "dependencies" in project.get("dynamic", []):
        report.add("WARN", "Зависимости", "Динамические зависимости нельзя определить статически")
    result: list[Requirement] = []
    raw_deps = project.get("dependencies", [])
    if not isinstance(raw_deps, list):
        report.add("WARN", "Зависимости", "project.dependencies должен быть списком")
        raw_deps = []
    for raw in raw_deps[:2000]:
        try:
            result.append(Requirement(raw))
        except (InvalidRequirement, TypeError):
            report.add("WARN", "Зависимости", f"Некорректная зависимость в pyproject.toml: {raw!r}")
    optional = project.get("optional-dependencies", {})
    if not isinstance(optional, dict):
        report.add("WARN", "Зависимости", "project.optional-dependencies должен быть таблицей")
    else:
        optional_count = 0
        for group, entries in list(optional.items())[:100]:
            if not isinstance(group, str) or not isinstance(entries, list):
                report.add("WARN", "Зависимости", f"Некорректная необязательная группа: {str(group)[:60]}")
                continue
            for raw in entries[:2000]:
                try:
                    Requirement(raw)
                    optional_count += 1
                except (InvalidRequirement, TypeError):
                    report.add("WARN", "Зависимости", f"Некорректная запись в extras [{group}]: {str(raw)[:60]}")
        if optional_count:
            report.add("INFO", "Зависимости", f"Необязательных зависимостей (extras): {optional_count}; установка не обязательна")
    requires_python = project.get("requires-python")
    if requires_python is not None and not isinstance(requires_python, str):
        report.add("WARN", "Зависимости", "project.requires-python должен быть строкой")
        requires_python = None
    if requires_python is not None:
        try:
            SpecifierSet(requires_python)
        except InvalidSpecifier:
            report.add("ERROR", "Зависимости", f"Некорректное requires-python: {requires_python[:100]}",
                       "Используйте PEP 440, например >=3.11,<4.")
            requires_python = None
    return result, requires_python


def _find_environment(root: Path) -> tuple[Path | None, Path | None, str | None]:
    for name in (".venv", "venv", "env"):
        env = root / name
        if not env.resolve().is_relative_to(root.resolve()):
            continue
        if not (env / "pyvenv.cfg").is_file() or not (env / "pyvenv.cfg").resolve().is_relative_to(root.resolve()):
            continue
        site = env / "Lib" / "site-packages"
        if not site.is_dir():
            options = sorted((env / "lib").glob("python*/site-packages"))
            site = next((entry for entry in options if entry.is_dir()), site)
        version = None
        try:
            cfg = (env / "pyvenv.cfg").read_text(encoding="utf-8")
            match = re.search(r"^version\s*=\s*([\d.]+)", cfg, flags=re.M | re.I)
            if match:
                version = match.group(1)
        except (OSError, UnicodeError):
            pass
        return env, (site if site.is_dir() and site.resolve().is_relative_to(root.resolve()) else None), version
    return None, None, None


def _installed_packages(site: Path, report: Report) -> dict[str, str]:
    installed: dict[str, str] = {}
    try:
        for dist in importlib.metadata.distributions(path=[str(site)]):
            try:
                name = dist.metadata.get("Name")
                if name:
                    installed[canonicalize_name(name)] = dist.version
            except (OSError, ValueError, KeyError):
                continue
    except (OSError, ValueError) as exc:
        report.add("ERROR", "Окружение", f"Не удалось прочитать метаданные пакетов: {exc}")
    return installed


def _analyze_python(folder: Path, source: str = "local") -> Report:
    """Static checks for Python projects, preserved from 0.2."""
    root = Path(folder).resolve()
    report = Report(root, source=source)
    if not root.is_dir():
        report.add("ERROR", "Проект", "Папка недоступна или не существует")
        return report

    for filename, title in (("README.md", "Документация"),
                            (".gitignore", "Настройки Git"),
                            ("LICENSE", "Лицензия")):
        if (root / filename).is_file():
            report.add("OK", "Проект", f"{title}: {filename}")
        else:
            report.add("WARN", "Проект", f"Отсутствует {filename} — {title.lower()}")

    scripts = list(root.glob("*.py"))
    report.add("INFO", "Проект", f"Python-файлов в корне: {len(scripts)}")

    requirements: list[Requirement] = []
    req_file = root / "requirements.txt"
    if req_file.is_file():
        report.add("OK", "Зависимости", "Найден requirements.txt")
        requirements += _load_requirements(root, req_file, report, set())
    py_deps, python_spec = _read_pyproject(root, report)
    if (root / "pyproject.toml").is_file():
        report.add("OK", "Зависимости", "Найден pyproject.toml")
    requirements += py_deps
    from manifest_checks import scan_additional_manifests
    requirements += scan_additional_manifests(root, report)
    from python_checks import check_dependency_conflicts, check_python_syntax
    check_dependency_conflicts(requirements, report)
    check_python_syntax(root, report)
    if not requirements:
        report.add("INFO", "Зависимости", "Проверяемые обязательные зависимости не объявлены (или формат не поддерживается)")
    else:
        report.add("INFO", "Зависимости", f"Объявлено записей зависимостей: {len(requirements)}")

    env, site, python_version = _find_environment(root)
    if env is None:
        if source == "github":
            report.add("SKIP", "Окружение", "GitHub ZIP не содержит локального Python-окружения — это нормально",
                       "Для проверки установленных пакетов скопируйте проект локально и подготовьте окружение.")
        else:
            report.add("WARN", "Окружение", "В корне не найдено .venv, venv или env с pyvenv.cfg",
                       "Для нового доверенного Python-проекта создайте: py -m venv .venv")
        report.add("INFO", "Окружение", "Проверка установленных пакетов пропущена: нет окружения")
        return report
    report.add("OK", "Окружение", f"Найдено: {env.name}")
    if python_version:
        report.add("INFO", "Окружение", f"Python окружения: {python_version}")
    if python_spec and python_version:
        try:
            supported = Version(python_version) in SpecifierSet(python_spec)
            report.add("OK" if supported else "ERROR", "Окружение",
                       f"Python {python_version} {'соответствует' if supported else 'не соответствует'} requires-python {python_spec}")
        except (InvalidSpecifier, InvalidVersion):
            report.add("WARN", "Окружение", f"Не удалось оценить requires-python: {python_spec}")
    if site is None:
        report.add("WARN", "Окружение", "Не найдена директория site-packages")
        return report

    installed = _installed_packages(site, report)
    report.add("INFO", "Окружение", f"Установлено пакетов (по метаданным): {len(installed)}")
    marker_environment = default_environment()
    if python_version:
        try:
            v = Version(python_version)
            marker_environment["python_version"] = f"{v.major}.{v.minor}"
            marker_environment["python_full_version"] = str(v)
        except InvalidVersion:
            pass
    seen: set[tuple[str, str]] = set()
    for requirement in requirements:
        key = (canonicalize_name(requirement.name), str(requirement.specifier))
        if key in seen:
            continue
        seen.add(key)
        if requirement.marker:
            try:
                if not requirement.marker.evaluate(environment=marker_environment):
                    report.add("SKIP", "Пакеты", f"{requirement}: условие окружения не выполняется")
                    continue
            except (ValueError, KeyError):
                report.add("WARN", "Пакеты", f"Не удалось проверить условие: {requirement}")
                continue
        found = installed.get(canonicalize_name(requirement.name))
        if found is None:
            report.add("ERROR", "Пакеты", f"Не установлен: {requirement.name} (требуется {requirement.specifier or 'любая версия'})",
                       "Сверьте манифест и установленные пакеты в выбранном виртуальном окружении.")
            continue
        if requirement.url:
            report.add("INFO", "Пакеты", f"{requirement.name} {found}: версия есть, источник URL не проверяется")
        try:
            good = not requirement.specifier or Version(found) in requirement.specifier
        except InvalidVersion:
            report.add("WARN", "Пакеты", f"Некорректная установленная версия {requirement.name}: {found}")
            continue
        if good:
            report.add("OK", "Пакеты", f"{requirement.name}: {found} подходит ({requirement.specifier or 'без ограничений'})")
        else:
            report.add("ERROR", "Пакеты", f"{requirement.name}: установлена {found}, требуется {requirement.specifier}")
    return report


def analyze_project(folder: Path, source: str = "local") -> Report:
    """Analyze supported local projects without executing project code.

    Node and Git checks are additive. Pure Node projects do not receive false
    warnings about missing Python virtual environments.
    """
    if source not in ("local", "github"):
        raise ValueError("Источник должен быть local или github")
    started = time.perf_counter()
    root = Path(folder).resolve()
    if not root.is_dir():
        report = Report(root, source=source)
        report.add("ERROR", "Проект", "Папка недоступна или не существует")
        return report

    has_python = any((root / f).is_file() for f in
                     ("requirements.txt", "pyproject.toml", "setup.py", "setup.cfg", "Pipfile", "main.py"))
    if not has_python:
        has_python = any(root.glob("*.py"))
    if has_python:
        report = _analyze_python(root, source=source)
        report.add("INFO", "Тип проекта", "Обнаружен Python")
    else:
        report = Report(root, source=source)
        for filename in ("README.md", "LICENSE", ".gitignore"):
            if (root / filename).is_file():
                report.add("OK", "Проект", f"Найден {filename}")
            else:
                report.add("WARN", "Проект", f"Отсутствует {filename}")

    from node_diagnostics import analyze_node
    from git_diagnostics import analyze_git

    has_node = (root / "package.json").is_file()
    if has_node:
        report.add("INFO", "Тип проекта", "Обнаружен Node.js")
        analyze_node(root, report)
    if not has_python and not has_node:
        report.add("WARN", "Тип проекта",
                   "Не обнаружены Python/Node.js манифесты; проведены общие проверки")
    analyze_git(root, report)
    from project_checks import analyze_project_hygiene
    from docker_diagnostics import analyze_docker
    from github_checks import analyze_github_readiness
    # Individual optional scanners should not prevent other results from being
    # returned if a project contains a malformed or inaccessible manifest.
    for caption, check in (
        ("Гигиена проекта", lambda: analyze_project_hygiene(root, report, has_python=has_python, has_node=has_node)),
        ("Docker", lambda: analyze_docker(root, report)),
        ("GitHub", lambda: analyze_github_readiness(root, report, has_python=has_python, has_node=has_node)),
    ):
        try:
            check()
        except (OSError, UnicodeError, ValueError, RecursionError) as exc:
            report.add("SKIP", caption, f"Часть проверки не выполнена ({type(exc).__name__})",
                       "Проверьте права доступа и корректность конфигурации.")
    elapsed = (time.perf_counter() - started) * 1000
    report.add("INFO", "Производительность", f"Время статического сканирования: {elapsed:.1f} мс (без сетевой загрузки)")
    return report

"""Additional *static*, bounded Python dependency manifest readers.

Supports a practical subset of Poetry, Pipenv, and setuptools declarative
metadata. Unsupported versions are explicitly skipped, never guessed.
Does not import a project, install packages, contact the network, or run tools.
"""
from __future__ import annotations

import configparser
import re
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Any

from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

if TYPE_CHECKING:
    from diagnostics import Report

MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_DEPENDENCIES = 1000
PACKAGE_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
POETRY_RANGE_RE = re.compile(r"^([\^~])(\d+(?:\.\d+){0,2})$")


def _read_toml(root: Path, filename: str, report: Report) -> dict[str, Any] | None:
    path = root / filename
    try:
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("ссылка выходит за пределы проекта")
        if path.stat().st_size > MAX_MANIFEST_BYTES:
            raise ValueError("размер превышает 2 МиБ")
        with path.open("rb") as file:
            data = tomllib.load(file)
        if not isinstance(data, dict):
            raise ValueError("ожидалась TOML-таблица")
        return data
    except (OSError, tomllib.TOMLDecodeError, ValueError, UnicodeError) as exc:
        report.add("WARN", "Менеджеры Python", f"{filename}: нельзя прочитать манифест ({type(exc).__name__})",
                   "Проверьте правильность TOML и размер файла.")
        return None


def _poetry_constraint(value: str) -> str | None:
    """Convert only confidently supported Poetry syntax to PEP 440.

    Note: Poetry and PEP 440 are not equivalent for all constraints.
    In uncertain cases, return None instead of misdiagnosing an installation.
    """
    value = value.strip()
    if value in ("", "*"):
        return ""
    if "||" in value:
        return None
    match = POETRY_RANGE_RE.fullmatch(value)
    if match:
        operator, text = match.groups()
        if len(text) > 48:
            return None  # Never parse unbounded untrusted integer components.
        chunks = [int(part) for part in text.split(".")]
        normalized = chunks + [0] * (3 - len(chunks))
        major, minor, patch = normalized
        if operator == "^":
            if len(chunks) == 1 and major == 0:
                upper = "1.0.0"
            elif len(chunks) == 2 and major == 0 and minor == 0:
                upper = "0.1.0"
            elif major != 0:
                upper = f"{major + 1}.0.0"
            elif minor != 0:
                upper = f"0.{minor + 1}.0"
            else:
                upper = f"0.0.{patch + 1}"
        elif len(chunks) == 1:
            upper = f"{major + 1}.0.0"
        else:
            upper = f"{major}.{minor + 1}.0"
        return f">={text},<{upper}"
    if value.startswith("~") or value.startswith("^"):
        return None
    if re.fullmatch(r"\d+(?:\.\d+){0,2}", value):
        value = "==" + value
    # Simple wildcard 1.* is a Poetry-compatible version constraint.
    if re.fullmatch(r"\d+(?:\.\d+)*\.\*", value):
        value = "==" + value
    # Accept plain PEP 440 constraints (not Poetry's bare '1.2.3').
    try:
        SpecifierSet(value)
        return value
    except InvalidSpecifier:
        return None


def _requirement(name: Any, spec: Any, report: Report, origin: str,
                 *, marker: str | None = None) -> Requirement | None:
    if not isinstance(name, str) or not PACKAGE_RE.fullmatch(name):
        report.add("WARN", "Менеджеры Python", f"{origin}: недопустимое имя пакета")
        return None
    if not isinstance(spec, str):
        report.add("WARN", "Менеджеры Python", f"{origin}: версия должна быть строкой")
        return None
    if marker is not None and not isinstance(marker, str):
        report.add("WARN", "Менеджеры Python", f"{origin}: некорректный marker")
        return None
    text = name + spec
    if marker:
        text += "; " + marker
    try:
        return Requirement(text)
    except InvalidRequirement:
        report.add("WARN", "Менеджеры Python", f"{origin}: неверное условие версии/marker")
        return None


def _parse_poetry(root: Path, report: Report) -> list[Requirement]:
    if not (root / "pyproject.toml").is_file():
        return []
    data = _read_toml(root, "pyproject.toml", report)
    if data is None:
        return []
    tool = data.get("tool", {})
    poetry = tool.get("poetry", {}) if isinstance(tool, dict) else {}
    if not isinstance(poetry, dict) or "dependencies" not in poetry:
        return []
    section = poetry["dependencies"]
    if not isinstance(section, dict):
        report.add("WARN", "Менеджеры Python", "Poetry: dependencies должен быть TOML-таблицей")
        return []

    # PEP 621 [project.dependencies] is the standardized source of truth when
    # present. Avoid reporting false conflicts against Poetry's legacy table.
    project = data.get("project", {})
    if isinstance(project, dict) and "dependencies" in project:
        report.add("INFO", "Менеджеры Python", "Poetry обнаружен; используются зависимости [project.dependencies] (PEP 621)")
        return []

    result: list[Requirement] = []
    optional_count = 0
    skipped = 0
    for name, definition in list(section.items())[:MAX_DEPENDENCIES]:
        if name == "python":
            continue
        spec: str | None = None
        marker = None
        if isinstance(definition, str):
            spec = definition
        elif isinstance(definition, dict):
            if definition.get("optional") is True:
                optional_count += 1
                continue
            if any(key in definition for key in ("git", "path", "url", "source", "develop")):
                skipped += 1
                continue
            if "python" in definition or "platform" in definition or "extras" in definition:
                # Environment-specific/extra packages are not unconditional.
                skipped += 1
                continue
            spec = definition.get("version", "*")
            marker = definition.get("markers")
        else:
            skipped += 1
            continue
        if not isinstance(spec, str):
            report.add("WARN", "Менеджеры Python", f"Poetry {str(name)[:60]}: некорректный version")
            continue
        converted = _poetry_constraint(spec)
        if converted is None:
            skipped += 1
            continue
        requirement = _requirement(name, converted, report, f"Poetry {str(name)[:60]}", marker=marker)
        if requirement is not None:
            result.append(requirement)
    if len(section) > MAX_DEPENDENCIES:
        report.add("WARN", "Менеджеры Python", "Poetry: обработаны только первые 1000 зависимостей")
    report.add("OK", "Менеджеры Python", f"Poetry: распознано обязательных зависимостей: {len(result)}")
    if optional_count:
        report.add("INFO", "Менеджеры Python", f"Poetry: необязательных зависимостей: {optional_count}")
    if skipped:
        report.add("SKIP", "Менеджеры Python", f"Poetry: сложных/неподдерживаемых записей пропущено: {skipped}",
                   "Сверьте условия напрямую в pyproject.toml. Сканер не выполняет poetry install.")
    if not (root / "poetry.lock").is_file():
        report.add("INFO", "Менеджеры Python", "Poetry lock-файл не обнаружен (для библиотек он может быть необязательным)")
    else:
        report.add("OK", "Менеджеры Python", "Обнаружен poetry.lock; его содержимое не проверяется")
    return result


def _parse_pipfile(root: Path, report: Report) -> list[Requirement]:
    if not (root / "Pipfile").is_file():
        return []
    data = _read_toml(root, "Pipfile", report)
    if data is None:
        return []
    section = data.get("packages", {})
    if not isinstance(section, dict):
        report.add("WARN", "Менеджеры Python", "Pipenv: [packages] должен быть TOML-таблицей")
        return []
    result: list[Requirement] = []
    skipped = 0
    for name, definition in list(section.items())[:MAX_DEPENDENCIES]:
        marker = None
        if isinstance(definition, str):
            spec = definition
        elif isinstance(definition, dict):
            if any(key in definition for key in ("git", "path", "file", "editable", "ref", "extras", "index")):
                skipped += 1
                continue
            spec = definition.get("version", "*")
            marker = definition.get("markers")
        else:
            skipped += 1
            continue
        if not isinstance(spec, str):
            report.add("WARN", "Менеджеры Python", f"Pipenv {str(name)[:60]}: некорректная версия")
            continue
        normalized = "" if spec.strip() == "*" else spec.strip()
        requirement = _requirement(name, normalized, report, f"Pipenv {str(name)[:60]}", marker=marker)
        if requirement is not None:
            result.append(requirement)
    if len(section) > MAX_DEPENDENCIES:
        report.add("WARN", "Менеджеры Python", "Pipenv: обработаны только первые 1000 зависимостей")
    optional = data.get("dev-packages", {})
    if isinstance(optional, dict) and optional:
        report.add("INFO", "Менеджеры Python", f"Pipenv: dev-пакетов: {min(len(optional), MAX_DEPENDENCIES)}, обязательная установка не проверяется")
    if skipped:
        report.add("SKIP", "Менеджеры Python", f"Pipenv: нестандартных записей пропущено: {skipped}")
    report.add("OK", "Менеджеры Python", f"Pipenv: распознано обязательных зависимостей: {len(result)}")
    if (root / "Pipfile.lock").is_file():
        report.add("OK", "Менеджеры Python", "Обнаружен Pipfile.lock; содержимое не анализируется")
    else:
        report.add("INFO", "Менеджеры Python", "Pipfile.lock отсутствует; для приложений рекомендуется lock-файл")
    return result


def _parse_setup_cfg(root: Path, report: Report) -> list[Requirement]:
    path = root / "setup.cfg"
    if not path.is_file():
        return []
    try:
        if not path.resolve().is_relative_to(root.resolve()) or path.stat().st_size > MAX_MANIFEST_BYTES:
            raise ValueError("файл вне проекта или больше 2 МиБ")
        cfg = configparser.ConfigParser(interpolation=None)
        cfg.read_string(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError, configparser.Error) as exc:
        report.add("WARN", "Менеджеры Python", f"setup.cfg: не удалось прочитать ({type(exc).__name__})")
        return []
    if not cfg.has_option("options", "install_requires"):
        return []
    lines = cfg.get("options", "install_requires").splitlines()
    result: list[Requirement] = []
    for raw in lines[:MAX_DEPENDENCIES]:
        value = raw.strip()
        if not value or value.startswith("#"):
            continue
        try:
            result.append(Requirement(value))
        except InvalidRequirement:
            report.add("WARN", "Менеджеры Python", "setup.cfg: некорректная запись install_requires")
    if len(lines) > MAX_DEPENDENCIES:
        report.add("WARN", "Менеджеры Python", "setup.cfg: обработаны только первые 1000 строк")
    if cfg.has_section("options.extras_require"):
        report.add("INFO", "Менеджеры Python", "setup.cfg: extras_require не включаются в обязательные зависимости")
    report.add("OK", "Менеджеры Python", f"setuptools setup.cfg: обязательных зависимостей: {len(result)}")
    return result


def scan_additional_manifests(root: Path, report: Report) -> list[Requirement]:
    """Read known declarative manifests; never execute setup.py or tool commands."""
    deps = _parse_poetry(root, report)
    deps += _parse_pipfile(root, report)
    deps += _parse_setup_cfg(root, report)
    return deps

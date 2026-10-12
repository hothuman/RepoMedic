"""Read-only Node.js project inspection. Does not run npm, node or scripts."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from diagnostics import Report

MAX_MANIFEST_BYTES = 2 * 1024 * 1024
PACKAGE_NAME_RE = re.compile(r"^(?:@[a-zA-Z0-9_.-]+/)?[a-zA-Z0-9_.-]+$")
NUMERIC = re.compile(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?$")
COMPARATOR = re.compile(r"^(>=|<=|>|<|=)?(\d+(?:\.\d+){0,2})$")


def _parse_version(value: str) -> tuple[int, int, int] | None:
    match = NUMERIC.fullmatch(value.strip())
    if not match:
        return None
    return tuple(int(piece) if piece is not None else 0 for piece in match.groups())  # type: ignore[return-value]


def _range_test(version: str, spec: str) -> bool | None:
    """Evaluate a deliberately small, explicit subset of npm semver.\n\n    None means unsupported syntax, NOT a failed requirement.\n    Prerelease, unions, aliases, tags and workspace ranges are unknown.\n    """
    actual = _parse_version(version)
    if actual is None:
        return None
    spec = spec.strip()
    if spec in ("*", "", "x", "X"):
        return True
    if "||" in spec or " - " in spec:
        return None
    matched = True
    for part in spec.split():
        if part.startswith("^") or part.startswith("~"):
            lower = _parse_version(part[1:])
            if lower is None:
                return None
            if part[0] == "~":
                upper = (lower[0], lower[1] + 1, 0)
            elif lower[0] > 0:
                upper = (lower[0] + 1, 0, 0)
            elif lower[1] > 0:
                upper = (0, lower[1] + 1, 0)
            else:
                upper = (0, 0, lower[2] + 1)
            matched = matched and lower <= actual < upper
            continue
        cmp_match = COMPARATOR.fullmatch(part)
        if not cmp_match:
            return None
        operator, target_raw = cmp_match.groups()
        target = _parse_version(target_raw)
        if target is None:
            return None
        if operator is None and target_raw.count(".") != 2:
            return None  # npm partial ranges need extra semantics
        ok = {
            ">=": actual >= target,
            "<=": actual <= target,
            ">": actual > target,
            "<": actual < target,
            "=": actual == target,
            None: actual == target,
        }[operator]
        matched = matched and ok
    return matched


def _read_json(path: Path, root: Path) -> dict:
    # Reject symlink escapes; don't read unexpectedly large files.
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("файл выходит за пределы проекта")
    if path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError("файл слишком большой (предел 2 МиБ)")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("корневой элемент JSON должен быть объектом")
    return data


def analyze_node(root: Path, report: Report) -> None:
    section = "Node.js"
    manifest = root / "package.json"
    try:
        package = _read_json(manifest, root)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        report.add("ERROR", section, f"Невозможно прочитать package.json: {exc}",
                   "Проверьте синтаксис JSON и права доступа.")
        return

    name = package.get("name", "(не указано)")
    report.add("OK", section, f"Найден package.json · {str(name)[:100]}")
    scripts = package.get("scripts", {})
    if isinstance(scripts, dict):
        report.add("INFO", section, "Доступные скрипты: " +
                   (", ".join(str(key)[:30] for key in list(scripts)[:15]) or "нет") +
                   " (не запускались)")
    else:
        report.add("WARN", section, "Некорректная секция scripts")

    engines = package.get("engines", {})
    if isinstance(engines, dict) and isinstance(engines.get("node"), str):
        report.add("INFO", section, f"Указанное требование Node.js: {engines['node'][:100]}")

    locks = [name for name in ("package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml", "bun.lock", "bun.lockb")
             if (root / name).is_file()]
    if not locks:
        report.add("WARN", section, "Не обнаружен lock-файл менеджера пакетов",
                   "Для воспроизводимой установки добавьте lock-файл выбранного менеджера.")
    elif len(locks) > 1:
        report.add("WARN", section, f"Найдено несколько lock-файлов: {', '.join(locks)}",
                   "Убедитесь, что проект использует один менеджер пакетов.")
    else:
        report.add("OK", section, f"Lock-файл: {locks[0]}")

    manager = package.get("packageManager")
    if isinstance(manager, str) and manager:
        manager_name = manager.split("@", 1)[0]
        expected = {"npm": {"package-lock.json", "npm-shrinkwrap.json"},
                    "pnpm": {"pnpm-lock.yaml"}, "yarn": {"yarn.lock"},
                    "bun": {"bun.lock", "bun.lockb"}}.get(manager_name)
        if expected and locks and not any(lock in expected for lock in locks):
            report.add("WARN", section, f"packageManager={manager_name}, но lock-файл другого менеджера: {', '.join(locks)}",
                       "Согласуйте поле packageManager и lock-файл; не запускайте установку из недоверенных источников.")
        else:
            report.add("INFO", section, f"Менеджер пакетов: {manager[:80]}")

    all_deps: list[tuple[str, str, str]] = []
    for key in ("dependencies", "devDependencies"):
        dependencies = package.get(key, {})
        if not isinstance(dependencies, dict):
            report.add("WARN", section, f"Секция {key} должна быть объектом")
            continue
        for dep_name, spec in dependencies.items():
            if not isinstance(dep_name, str) or not isinstance(spec, str):
                report.add("WARN", section, f"Некорректная запись в {key}")
                continue
            all_deps.append((dep_name, spec, key))
    report.add("INFO", section, f"Объявлено прямых зависимостей: {len(all_deps)}")

    modules = root / "node_modules"
    if not modules.is_dir():
        if report.source == "github":
            report.add("SKIP", section, "Проверка установленных Node.js-пакетов пропущена для GitHub ZIP",
                       "Это исходники без node_modules; скачайте проект локально для проверки установленных версий.")
            return
        if all_deps:
            report.add("WARN", section, "node_modules отсутствует: проверка установленных пакетов пропущена",
                       "Установите зависимости подходящим менеджером только после проверки источника проекта.")
        return
    report.add("OK", section, "Обнаружена папка node_modules")
    for dep_name, spec, category in all_deps[:300]:
        if not PACKAGE_NAME_RE.fullmatch(dep_name) or dep_name in (".", "..") or "/../" in dep_name:
            report.add("WARN", "Node-пакеты", f"Некорректное имя пакета: {dep_name[:80]}")
            continue
        pkg_manifest = modules / dep_name / "package.json"
        if not pkg_manifest.is_file():
            report.add("ERROR", "Node-пакеты", f"Не установлен: {dep_name} ({category}, {spec})",
                       "Проверьте node_modules и lock-файл; при необходимости установите зависимости.")
            continue
        try:
            installed = _read_json(pkg_manifest, root)
            version = installed.get("version")
            if not isinstance(version, str):
                raise ValueError("не указана версия")
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            report.add("WARN", "Node-пакеты", f"Не удалось проверить {dep_name}: {exc}")
            continue
        matches = _range_test(version, spec)
        if matches is None:
            report.add("SKIP", "Node-пакеты", f"{dep_name}: установлен {version}; диапазон {spec} не поддерживается статическим анализатором")
        elif matches:
            report.add("OK", "Node-пакеты", f"{dep_name}: {version} соответствует {spec}")
        else:
            report.add("ERROR", "Node-пакеты", f"{dep_name}: установлен {version}, требуется {spec}",
                       "Сверьте версию с lock-файлом и установите совместимую зависимость.")
    if len(all_deps) > 300:
        report.add("WARN", section, "Проверены только первые 300 прямых зависимостей")

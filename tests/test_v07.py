"""Cross-platform regression tests for v0.7 GitHub and Docker static checks."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path, PureWindowsPath
from unittest.mock import patch

from diagnostics import analyze_project
from docker_diagnostics import _instructions, _display_path


class V07Tests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / "README.md").write_text("# demo", encoding="utf-8")
        (self.root / "LICENSE").write_text("MIT", encoding="utf-8")
        (self.root / ".gitignore").write_text(".env\n", encoding="utf-8")
        (self.root / "package.json").write_text('{"name":"sample","dependencies":{}}', encoding="utf-8")
        (self.root / "package-lock.json").write_text("{}", encoding="utf-8")

    def scan(self):
        return analyze_project(self.root, source="github")

    def has(self, report, needle, level=None):
        return any(needle in f.message and (level is None or f.level == level) for f in report.findings)

    def test_basic_clean_dockerfile(self):
        (self.root / "Dockerfile").write_text("FROM python:3.13-slim\nWORKDIR /app\nUSER 10001\n", encoding="utf-8")
        report = self.scan()
        self.assertTrue(self.has(report, "Dockerfile: прочитано инструкций", "OK"))
        self.assertFalse(self.has(report, "без фиксированной версии"))
        self.assertFalse(self.has(report, "не задан USER"))

    def test_latest_image_and_missing_user(self):
        (self.root / "Dockerfile").write_text("FROM python:latest\nRUN echo hi\n", encoding="utf-8")
        report = self.scan()
        self.assertTrue(self.has(report, "без фиксированной версии", "WARN"))
        self.assertTrue(self.has(report, "не задан USER", "WARN"))

    def test_multistage_final_user(self):
        (self.root / "Dockerfile").write_text("FROM python:3.13 AS builder\nRUN echo hi\nFROM builder AS runtime\nUSER 1000\n", encoding="utf-8")
        report = self.scan()
        self.assertFalse(self.has(report, "не задан USER"))
        self.assertTrue(self.has(report, "этапов 2"))

    def test_secret_name_no_value_leak(self):
        (self.root / "Dockerfile").write_text("FROM python:3.13\nENV API_TOKEN=very-private-string\nUSER 1000\n", encoding="utf-8")
        report = self.scan()
        self.assertTrue(self.has(report, "возможный секрет", "WARN"))
        self.assertNotIn("very-private-string", report.to_json())

    def test_add_url_warns(self):
        (self.root / "Dockerfile").write_text("FROM alpine:3.21\nADD https://example.com/install /tmp/\nUSER 1000\n", encoding="utf-8")
        self.assertTrue(self.has(self.scan(), "ADD загружает URL", "WARN"))

    def test_curl_piped_shell(self):
        (self.root / "Dockerfile").write_text("FROM alpine:3.21\nRUN curl -fsSL https://example.com/i.sh | bash\nUSER 1000\n", encoding="utf-8")
        self.assertTrue(self.has(self.scan(), "напрямую в shell", "WARN"))

    def test_copy_dot_requires_dockerignore(self):
        (self.root / "Dockerfile").write_text("FROM alpine:3.21\nCOPY . /app\nUSER 1000\n", encoding="utf-8")
        self.assertTrue(self.has(self.scan(), "без .dockerignore", "WARN"))
        (self.root / ".dockerignore").write_text(".git\n.env\n", encoding="utf-8")
        self.assertFalse(self.has(self.scan(), "без .dockerignore"))

    def test_empty_dockerfile_detected(self):
        (self.root / "Dockerfile").write_text("# comment", encoding="utf-8")
        self.assertTrue(self.has(self.scan(), "нет инструкции FROM", "ERROR"))

    def test_dockerfile_backslash_continuation(self):
        commands = list(_instructions(["FROM alpine:3.21", "RUN curl -fsSL \\", "https://example.com | bash", "USER 1000"]))
        self.assertIn("curl -fsSL https://example.com", commands[1][2])

    def test_bounded_large_dockerfile_skipped(self):
        (self.root / "Dockerfile").write_bytes(b"#" * (1024 * 1024 + 1))
        self.assertTrue(self.has(self.scan(), "более 1 МиБ", "SKIP"))

    def test_windows_docker_path_display_is_posix(self):
        actual = _display_path(
            PureWindowsPath(r"C:\\repo\\docker\\Dockerfile.dev"),
            PureWindowsPath(r"C:\\repo"),
        )
        self.assertEqual(actual, "docker/Dockerfile.dev")

    def test_docker_subfolder_dockerfiles(self):
        folder = self.root / "docker"
        folder.mkdir()
        (folder / "Dockerfile.dev").write_text("FROM node:22\nUSER 1000\n", encoding="utf-8")
        self.assertTrue(self.has(self.scan(), "docker/Dockerfile.dev", "OK"))

    def test_compose_privileged_socket_and_latest(self):
        (self.root / "compose.yaml").write_text('services:\n  web:\n    image: nginx:latest\n    privileged: true\n    volumes:\n      - /var/run/docker.sock:/var/run/docker.sock\n', encoding="utf-8")
        report = self.scan()
        for needle in ("privileged: true", "Docker socket", "без фиксированной версии", "найдено служб 1"):
            self.assertTrue(self.has(report, needle), needle)

    def test_compose_host_network(self):
        (self.root / "docker-compose.yml").write_text("services:\n  web:\n    network_mode: host\n", encoding="utf-8")
        self.assertTrue(self.has(self.scan(), "network_mode: host", "WARN"))

    def test_compose_missing_services_warns(self):
        (self.root / "compose.yml").write_text("version: '3'\n", encoding="utf-8")
        self.assertTrue(self.has(self.scan(), "не найден блок services", "WARN"))

    def test_no_docker_is_info_not_error(self):
        report = self.scan()
        self.assertTrue(self.has(report, "Dockerfile/Compose не обнаружены", "INFO"))
        self.assertFalse(any(f.level == "ERROR" and f.section.startswith("Docker") for f in report.findings))

    def test_workflows_action_tag_warning(self):
        w = self.root / ".github" / "workflows"
        w.mkdir(parents=True)
        (w / "test.yml").write_text("name: CI\njobs:\n  test:\n    steps:\n      - uses: actions/checkout@v4\n", encoding="utf-8")
        report = self.scan()
        self.assertTrue(self.has(report, "изменяемому тегу", "WARN"))

    def test_workflows_sha_pinned_ok(self):
        w = self.root / ".github" / "workflows"
        w.mkdir(parents=True)
        (w / "test.yml").write_text("jobs:\n  test:\n    steps:\n      - uses: actions/checkout@" + "a" * 40, encoding="utf-8")
        self.assertFalse(self.has(self.scan(), "изменяемому тегу"))

    def test_local_actions_ignored(self):
        w = self.root / ".github" / "workflows"
        w.mkdir(parents=True)
        (w / "test.yml").write_text("steps:\n - uses: ./my-action\n", encoding="utf-8")
        self.assertFalse(self.has(self.scan(), "action без закреплённой версии"))

    def test_workflow_write_all_warning(self):
        w = self.root / ".github" / "workflows"
        w.mkdir(parents=True)
        (w / "test.yaml").write_text("permissions: write-all\n", encoding="utf-8")
        self.assertTrue(self.has(self.scan(), "permissions: write-all", "WARN"))

    def test_pull_request_target_checkout_warning(self):
        w = self.root / ".github" / "workflows"
        w.mkdir(parents=True)
        (w / "test.yml").write_text("on:\n  pull_request_target:\nsteps:\n - uses: actions/checkout@v4\n", encoding="utf-8")
        self.assertTrue(self.has(self.scan(), "pull_request_target", "WARN"))

    def test_large_workflow_is_skipped(self):
        w = self.root / ".github" / "workflows"
        w.mkdir(parents=True)
        (w / "test.yml").write_bytes(b"#" * (512 * 1024 + 1))
        self.assertTrue(self.has(self.scan(), "слишком большой файл", "SKIP"))

    def test_missing_github_ci_is_info(self):
        self.assertTrue(self.has(self.scan(), "GitHub Actions workflows не найдены", "INFO"))

    def test_security_and_contributing_found(self):
        (self.root / "SECURITY.md").write_text("contact", encoding="utf-8")
        (self.root / "CONTRIBUTING.md").write_text("PRs", encoding="utf-8")
        report = self.scan()
        self.assertTrue(self.has(report, "Политика сообщения об уязвимостях найдена", "OK"))
        self.assertTrue(self.has(report, "Инструкция для участников найдена", "OK"))

    def test_report_version_and_time(self):
        report = self.scan()
        data = json.loads(report.to_json())
        self.assertEqual(data["version"], "1.0.0")
        self.assertTrue(self.has(report, "Время статического сканирования", "INFO"))

    def test_fault_in_optional_scanner_does_not_abort(self):
        with patch("docker_diagnostics.analyze_docker", side_effect=OSError("test")):
            report = self.scan()
        self.assertTrue(self.has(report, "Часть проверки не выполнена", "SKIP"))
        self.assertTrue(self.has(report, "README.md", "OK"))

    def test_html_report_has_current_version(self):
        from html_report import render_html_report
        html = render_html_report(self.scan())
        self.assertIn("Версия 1.0.0", html)


if __name__ == "__main__":
    unittest.main()

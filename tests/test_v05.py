"""RepoMedic v0.5 regression cases. Uses only local temporary directories."""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from cli import main as cli_main
from diagnostics import analyze_project
from html_report import render_html_report
from python_checks import MAX_BYTES_PER_FILE


class TestPythonV05(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / "README.md").write_text("# Test", encoding="utf-8")
        (self.root / "LICENSE").write_text("MIT", encoding="utf-8")
        (self.root / ".gitignore").write_text(".venv/\n", encoding="utf-8")
        (self.root / "requirements.txt").write_text("# empty\n", encoding="utf-8")

    def scan(self, source="github"):
        return analyze_project(self.root, source=source)

    def messages(self, report, section=None):
        return [f for f in report.findings if section is None or f.section == section]

    def test_valid_python_source(self):
        (self.root / "script.py").write_text("def hello():\n    return 42\n", encoding="utf-8")
        report = self.scan()
        self.assertTrue(any(f.level == "OK" and "Проверено Python-файлов: 1" in f.message
                            for f in self.messages(report, "Синтаксис Python")))
        self.assertFalse(any(f.level == "ERROR" for f in self.messages(report, "Синтаксис Python")))

    def test_syntax_error_reporting(self):
        (self.root / "broken.py").write_text("def x(:\n    pass\n", encoding="utf-8")
        report = self.scan()
        self.assertTrue(any(f.level == "ERROR" and "broken.py" in f.message
                            for f in self.messages(report, "Синтаксис Python")))
        self.assertTrue(any(f.advice for f in self.messages(report, "Синтаксис Python") if f.level == "ERROR"))

    def test_nested_python_syntax(self):
        path = self.root / "src" / "pkg"
        path.mkdir(parents=True)
        (path / "bad.py").write_text("for x in:\n    pass\n", encoding="utf-8")
        report = self.scan()
        self.assertTrue(any("src/pkg/bad.py" in f.message for f in self.messages(report, "Синтаксис Python")))

    def test_virtual_env_not_scanned(self):
        hidden = self.root / ".venv" / "Scripts"
        hidden.mkdir(parents=True)
        (hidden / "bad.py").write_text("this is not python(\n", encoding="utf-8")
        (self.root / "good.py").write_text("ok = 1\n", encoding="utf-8")
        report = self.scan()
        self.assertFalse(any("bad.py" in f.message for f in report.findings))

    def test_node_modules_not_scanned(self):
        nested = self.root / "node_modules" / "module"
        nested.mkdir(parents=True)
        (nested / "bad.py").write_text("!!!\n", encoding="utf-8")
        report = self.scan()
        self.assertFalse(any("bad.py" in f.message for f in report.findings))

    def test_large_python_source_skipped(self):
        (self.root / "huge.py").write_bytes(b"a" * (MAX_BYTES_PER_FILE + 1))
        report = self.scan()
        self.assertTrue(any(f.level == "SKIP" and "Пропущено файлов" in f.message
                            for f in self.messages(report, "Синтаксис Python")))
        self.assertFalse(any(f.level == "ERROR" and "huge.py" in f.message for f in report.findings))

    def test_syntax_check_does_not_execute_python(self):
        marker = self.root / "must-not-exist.txt"
        payload = f'from pathlib import Path\nPath({str(marker)!r}).write_text("executed")\n'
        (self.root / "unsafe.py").write_text(payload, encoding="utf-8")
        report = self.scan()
        self.assertFalse(marker.exists())
        self.assertTrue(any(f.level == "OK" and "Проверено Python" in f.message
                            for f in self.messages(report, "Синтаксис Python")))

    def test_python_source_encoding_cookie(self):
        (self.root / "latin1.py").write_bytes(b"# coding: latin-1\nlabel = '\xe9'\n")
        report = self.scan()
        self.assertFalse(any(f.level == "ERROR" for f in self.messages(report, "Синтаксис Python")))

    def test_symlink_python_file_not_scanned(self):
        with tempfile.TemporaryDirectory() as outside:
            foreign = Path(outside) / "secret.py"
            foreign.write_text("this is not valid python !!!\n", encoding="utf-8")
            try:
                (self.root / "link.py").symlink_to(foreign)
            except (OSError, NotImplementedError):
                self.skipTest("Cannot create symlink on this platform")
            report = self.scan()
            self.assertNotIn("secret.py", report.to_text())
            self.assertFalse(any(f.level == "ERROR" and "link.py" in f.message for f in report.findings))

    def test_conflicting_exact_pins(self):
        (self.root / "requirements.txt").write_text("demo==1.0\ndemo==2.0\n", encoding="utf-8")
        report = self.scan()
        self.assertTrue(any(f.level == "ERROR" and "demo" in f.message
                            for f in self.messages(report, "Конфликты зависимостей")))

    def test_conflicting_exact_and_range(self):
        (self.root / "requirements.txt").write_text("demo==1.0\n", encoding="utf-8")
        (self.root / "pyproject.toml").write_text('[project]\ndependencies = ["demo>=2"]\n', encoding="utf-8")
        report = self.scan()
        self.assertTrue(any(f.level == "ERROR" and "demo" in f.message
                            for f in self.messages(report, "Конфликты зависимостей")))

    def test_compatible_exact_and_range(self):
        (self.root / "requirements.txt").write_text("demo==1.0\n", encoding="utf-8")
        (self.root / "pyproject.toml").write_text('[project]\ndependencies = ["demo>=1,<2"]\n', encoding="utf-8")
        report = self.scan()
        self.assertFalse(any(f.level == "ERROR" for f in self.messages(report, "Конфликты зависимостей")))

    def test_markers_not_wrongly_flagged(self):
        (self.root / "requirements.txt").write_text(
            'demo==1.0; python_version < "3.11"\ndemo==2.0; python_version >= "3.11"\n', encoding="utf-8"
        )
        report = self.scan()
        self.assertFalse(any(f.level == "ERROR" for f in self.messages(report, "Конфликты зависимостей")))

    def test_optional_dependencies_not_required(self):
        (self.root / "pyproject.toml").write_text(
            '[project]\nname = "app"\ndependencies = []\n'
            '[project.optional-dependencies]\nextra = ["nonexistent-package==1.0"]\n', encoding="utf-8")
        report = self.scan()
        self.assertTrue(any("Необязательных зависимостей" in f.message for f in report.findings))
        self.assertFalse(any(f.level == "ERROR" and "nonexistent-package" in f.message for f in report.findings))

    def test_invalid_optional_group_is_warning(self):
        (self.root / "pyproject.toml").write_text('[project]\nname = "app"\n'
            '[project.optional-dependencies]\nextra = "not a list"\n', encoding="utf-8")
        report = self.scan()
        self.assertTrue(any(f.level == "WARN" and "extra" in f.message for f in report.findings))

    def test_invalid_requires_python_without_venv(self):
        (self.root / "pyproject.toml").write_text('[project]\nrequires-python = "???"\n', encoding="utf-8")
        report = self.scan()
        self.assertTrue(any(f.level == "ERROR" and "requires-python" in f.message for f in report.findings))

    def test_json_report_version_and_syntax(self):
        (self.root / "bad.py").write_text("print(\n", encoding="utf-8")
        data = json.loads(self.scan().to_json())
        self.assertEqual(data["version"], "1.0.0")
        self.assertTrue(any(f["section"] == "Синтаксис Python" for f in data["findings"]))

    def test_cli_reports_syntax_failure(self):
        (self.root / "bad.py").write_text("def bad(:\n", encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            status = cli_main([str(self.root)])
        self.assertEqual(status, 1)

    def test_html_escapes_bad_filename(self):
        # "&" is valid in filenames on Windows, unlike "<" and ">".
        # It still must be HTML-escaped in the exported report.
        (self.root / "bad&unsafe.py").write_text("def bad(:\n", encoding="utf-8")
        report = self.scan()
        html = render_html_report(report)
        self.assertNotIn("bad&unsafe.py", html)
        self.assertIn("bad&amp;unsafe.py", html)


if __name__ == "__main__":
    unittest.main()

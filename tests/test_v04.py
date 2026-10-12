import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from cli import main as cli_main
from diagnostics import Report, analyze_project
from html_report import render_html_report


class TestV04(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "README.md").write_text("# Demo", encoding="utf-8")
        (self.root / "LICENSE").write_text("MIT", encoding="utf-8")
        (self.root / ".gitignore").write_text(".venv/\nnode_modules/\n", encoding="utf-8")

    def test_github_python_does_not_require_local_venv(self):
        (self.root / "requirements.txt").write_text("example>=1\n")
        report = analyze_project(self.root, source="github")
        self.assertTrue(any(f.level == "SKIP" and "GitHub ZIP" in f.message for f in report.findings))
        self.assertFalse(any(f.level == "WARN" and "venv" in f.message for f in report.findings))
        self.assertEqual(report.source, "github")
        self.assertEqual(json.loads(report.to_json())["source"], "github")

    def test_github_node_does_not_require_node_modules(self):
        (self.root / "package.json").write_text('{"dependencies":{"tool":"^1.0.0"}}')
        (self.root / "package-lock.json").write_text('{}')
        report = analyze_project(self.root, source="github")
        self.assertTrue(any(f.level == "SKIP" and "Node.js" in f.section for f in report.findings))
        self.assertFalse(any(f.level == "WARN" and "node_modules отсутствует" in f.message for f in report.findings))

    def test_local_missing_environment_still_warns(self):
        (self.root / "requirements.txt").write_text("example>=1\n")
        report = analyze_project(self.root)
        self.assertTrue(any(f.level == "WARN" and "venv" in f.message for f in report.findings))

    def test_unknown_source_rejected(self):
        with self.assertRaises(ValueError):
            analyze_project(self.root, source="remote-unknown")

    def test_package_manager_lock_mismatch(self):
        (self.root / "package.json").write_text('{"packageManager":"pnpm@9.3.0"}')
        (self.root / "package-lock.json").write_text('{}')
        report = analyze_project(self.root)
        self.assertTrue(any(f.level == "WARN" and "packageManager=pnpm" in f.message for f in report.findings))

    def test_package_manager_lock_agrees(self):
        (self.root / "package.json").write_text('{"packageManager":"npm@10.3.0"}')
        (self.root / "package-lock.json").write_text('{}')
        report = analyze_project(self.root)
        self.assertFalse(any("packageManager=npm" in f.message and f.level == "WARN" for f in report.findings))

    def test_env_not_ignored_warns_without_reading_value(self):
        (self.root / ".env").write_text("SECRET_ACCESS_KEY=do-not-print")
        report = analyze_project(self.root)
        self.assertTrue(any(f.level == "WARN" and ".env" in f.message for f in report.findings))
        self.assertNotIn("do-not-print", report.to_text())
        self.assertNotIn("do-not-print", report.to_json())

    def test_env_ignored(self):
        (self.root / ".env").write_text("KEY=hidden")
        (self.root / ".gitignore").write_text(".env\n")
        report = analyze_project(self.root)
        self.assertTrue(any(f.level == "OK" and ".env" in f.message for f in report.findings))

    def test_venv_gitignore_warning(self):
        (self.root / "requirements.txt").write_text("example\n")
        (self.root / ".git").mkdir()
        (self.root / ".venv").mkdir()
        (self.root / ".gitignore").write_text("__pycache__/\n")
        report = analyze_project(self.root)
        self.assertTrue(any(".venv присутствует" in f.message and f.level == "WARN" for f in report.findings))

    def test_invalid_pyproject_dependency_value_handled(self):
        (self.root / "pyproject.toml").write_text('[project]\ndependencies = "wrong"\n')
        report = analyze_project(self.root)
        self.assertTrue(any("project.dependencies должен быть списком" in f.message for f in report.findings))

    def test_invalid_requires_python_type_handled(self):
        (self.root / "pyproject.toml").write_text('[project]\nrequires-python = 123\n')
        report = analyze_project(self.root)
        self.assertTrue(any("project.requires-python должен быть строкой" in f.message for f in report.findings))

    def test_large_requirements_bounded(self):
        (self.root / "requirements.txt").write_bytes(b"#\n" * 1_100_000)
        report = analyze_project(self.root)
        self.assertTrue(any("2 МиБ" in f.message for f in report.findings))

    def test_html_escapes_untrusted_text(self):
        report = Report(self.root)
        report.add("WARN", '<script>alert("bad")</script>', '<img src=x onerror=alert(1)>', '<b>unsafe</b>')
        page = render_html_report(report)
        self.assertNotIn('<script>alert("bad")</script>', page)
        self.assertNotIn('<img src=x onerror=alert(1)>', page)
        self.assertNotIn('<b>unsafe</b>', page)
        self.assertIn('&lt;script&gt;', page)
        self.assertIn('&lt;img', page)
        self.assertIn('&lt;b&gt;', page)

    def test_cli_json_output(self):
        output = self.root / "results.json"
        with contextlib.redirect_stderr(io.StringIO()):
            status = cli_main([str(self.root), "--format", "json", "--output", str(output)])
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["version"], "1.0.0")

    def test_cli_strict_warnings(self):
        with contextlib.redirect_stdout(io.StringIO()):
            status = cli_main([str(self.root), "--fail-on-warning"])
        self.assertEqual(status, 1)

    def test_cli_missing_folder_exit_2(self):
        with contextlib.redirect_stderr(io.StringIO()):
            status = cli_main([str(self.root / "notfound")])
        self.assertEqual(status, 2)

    def test_cli_html_output(self):
        output = self.root / "results.html"
        with contextlib.redirect_stderr(io.StringIO()):
            status = cli_main([str(self.root), "--format", "html", "--output", str(output)])
        self.assertEqual(status, 0)
        self.assertIn("<!doctype html>", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

class TestSymlinks(unittest.TestCase):
    def test_external_git_config_not_read(self):
        from diagnostics import analyze_project
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp)
            git = root / ".git"
            git.mkdir()
            foreign = Path(outside) / "outside_config"
            foreign.write_text('[remote "origin"]\nurl = https://github.com/leaked/leaked\n')
            try:
                (git / "config").symlink_to(foreign)
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks need extra privileges on this platform")
            report = analyze_project(root)
            self.assertNotIn('GitHub: leaked/leaked', report.to_text())

    def test_external_python_site_packages_skipped(self):
        from diagnostics import analyze_project
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp)
            (root / "requirements.txt").write_text("example>=1\n")
            env = root / ".venv"
            env.mkdir()
            (env / "pyvenv.cfg").write_text("version = 3.13.0\n")
            lib = env / "Lib"
            lib.mkdir()
            try:
                (lib / "site-packages").symlink_to(Path(outside), target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks need extra privileges on this platform")
            report = analyze_project(root)
            self.assertTrue(any(f.level == "WARN" and "site-packages" in f.message for f in report.findings))

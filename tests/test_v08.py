"""Stability regressions; portable between Windows and Linux."""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from cli import main as cli_main
from diagnostics import Report, analyze_project
from github_downloader import DownloadError, parse_github_url, safe_extract
from html_report import render_html_report
from report_io import atomic_save_text


class StabilityV08(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def archive(self, files):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as z:
            for name, contents in files:
                z.writestr(name, contents)
        buffer.seek(0)
        return zipfile.ZipFile(buffer)

    def assert_archive_rejected(self, paths):
        with self.archive(paths) as z:
            with self.assertRaises(DownloadError):
                safe_extract(z, self.root)

    def test_windows_reserved_con(self):
        self.assert_archive_rejected([("repo-main/CON.py", "test")])

    def test_windows_reserved_nul_extension(self):
        self.assert_archive_rejected([("repo-main/NUL.txt", "hello")])

    def test_windows_com_port_is_reserved(self):
        self.assert_archive_rejected([("repo-main/COM1.log", "hello")])

    def test_archive_ads_colon(self):
        self.assert_archive_rejected([("repo-main/notes.txt:metadata", "hello")])

    def test_archive_forbidden_question_mark(self):
        self.assert_archive_rejected([("repo-main/what?.txt", "hello")])

    def test_archive_trailing_dot(self):
        self.assert_archive_rejected([("repo-main/name./f.txt", "hello")])

    def test_archive_empty_component(self):
        self.assert_archive_rejected([("repo-main/folder//bad.txt", "hello")])

    def test_archive_duplicate_casefold(self):
        self.assert_archive_rejected([
            ("repo-main/Foo.py", "one"), ("repo-main/foo.py", "two")
        ])

    def test_archive_duplicate_identical(self):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            self.assert_archive_rejected([
                ("repo-main/file.py", "one"), ("repo-main/file.py", "two")
            ])

    def test_archive_file_as_parent(self):
        self.assert_archive_rejected([
            ("repo-main/package", "one"), ("repo-main/package/nested", "two")
        ])

    def test_archive_file_as_parent_reverse_order(self):
        self.assert_archive_rejected([
            ("repo-main/package/nested", "two"), ("repo-main/package", "one")
        ])

    def test_archive_multiple_top_level_roots(self):
        self.assert_archive_rejected([("repo-main/a.py", "one"), ("other-main/b.py", "two")])

    def test_archive_valid_nested_files(self):
        with self.archive([("repo-main/dir/good.py", "print(1)"), ("repo-main/README.md", "hi")]) as z:
            extracted = safe_extract(z, self.root)
        self.assertEqual((extracted / "dir" / "good.py").read_text(), "print(1)")

    def test_archive_case_alias_preflight_writes_nothing(self):
        with self.archive([("repo-main/Good.txt", "good"), ("repo-main/good.txt", "bad")]) as z:
            with self.assertRaises(DownloadError):
                safe_extract(z, self.root)
        self.assertFalse((self.root / "repo-main").exists())

    def test_archive_extraction_limit(self):
        with self.archive([("repo-main/good.txt", "123456")]) as z:
            with patch("github_downloader.EXPANDED_LIMIT", 5):
                with self.assertRaises(DownloadError):
                    safe_extract(z, self.root)

    def test_github_does_not_accept_http(self):
        with self.assertRaises(DownloadError):
            parse_github_url("http://github.com/org/project")

    def test_atomic_write_unicode(self):
        out = self.root / "report.html"
        atomic_save_text(out, "Привет 🍀\n")
        self.assertEqual(out.read_text(encoding="utf-8"), "Привет 🍀\n")
        self.assertEqual(list(self.root.glob(".repomedic-*")), [])

    def test_atomic_failure_preserves_existing_file(self):
        out = self.root / "report.txt"
        out.write_text("old", encoding="utf-8")
        with patch("report_io.os.replace", side_effect=OSError("disk error")):
            with self.assertRaises(OSError):
                atomic_save_text(out, "new")
        self.assertEqual(out.read_text(encoding="utf-8"), "old")
        self.assertEqual(list(self.root.glob(".repomedic-*")), [])

    def test_atomic_missing_parent_leaves_no_file(self):
        with self.assertRaises(OSError):
            atomic_save_text(self.root / "does-not-exist" / "report.txt", "data")
        self.assertFalse((self.root / "does-not-exist").exists())

    def test_cli_success_exit_code_zero(self):
        (self.root / "package.json").write_text('{"name":"demo","dependencies":{}}', encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = cli_main([str(self.root), "--format", "json"])
        self.assertEqual(result, 0)

    def test_cli_errors_exit_code_one(self):
        (self.root / "pyproject.toml").write_text("[project\n", encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = cli_main([str(self.root)])
        self.assertEqual(result, 1)

    def test_cli_invalid_folder_exit_code_two(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = cli_main([str(self.root / "does-not-exist")])
        self.assertEqual(result, 2)

    def test_cli_fail_on_warning(self):
        (self.root / "main.py").write_text("pass\n", encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = cli_main([str(self.root), "--fail-on-warning"])
        self.assertEqual(result, 1)

    def test_cli_write_json(self):
        (self.root / "package.json").write_text('{"name":"demo","dependencies":{}}', encoding="utf-8")
        out = self.root / "export.json"
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = cli_main([str(self.root), "--format", "json", "--output", str(out)])
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["version"], "1.0.0")

    def test_html_escaping_of_untrusted_strings(self):
        report = Report(self.root / "<img onerror=alert(1)>")
        report.add("WARN", "<script>", "<img src=x>", "</p><script>alert(1)</script>")
        html = render_html_report(report)
        self.assertNotIn("<script>", html)
        self.assertNotIn("<img onerror=alert(1)>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("Версия 1.0.0", html)

    def test_json_and_text_versions_are_consistent(self):
        report = analyze_project(self.root)
        self.assertIn("REPOMEDIC 1.0.0", report.to_text())
        self.assertEqual(json.loads(report.to_json())["version"], "1.0.0")


if __name__ == "__main__":
    unittest.main()

"""Release-version, package, CI and safety regression tests; no GUI runtime required."""
from __future__ import annotations
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from diagnostics import Report
from github_downloader import parse_github_url
from html_report import render_html_report
from version import __version__, DISPLAY_VERSION
from scripts.check_release import validate_tag, main as release_main


class ReleaseTests(unittest.TestCase):
    def test_semver(self):
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+$")

    def test_major_release(self):
        self.assertEqual(__version__, "1.0.0")

    def test_display_version(self):
        self.assertEqual(DISPLAY_VERSION, "v1.0")

    def test_matching_tag(self):
        self.assertTrue(validate_tag("v1.0.0"))

    def test_rejects_other_version(self):
        self.assertFalse(validate_tag("v0.9.1"))

    def test_rejects_prefix_version(self):
        self.assertFalse(validate_tag("v1.0.0-beta"))

    def test_rejects_injection(self):
        self.assertFalse(validate_tag("v1.0.0; rm -rf /"))

    def test_tag_guard_correct(self):
        self.assertEqual(release_main(["--tag", "v1.0.0"]), 0)

    def test_tag_guard_wrong(self):
        self.assertEqual(release_main(["--tag", "v2.0.0"]), 2)

    def test_json_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Report(Path(tmp))
            self.assertEqual(json.loads(report.to_json())["version"], __version__)

    def test_txt_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIn(f"REPOMEDIC {__version__}", Report(Path(tmp)).to_text())

    def test_html_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIn(f"Версия {__version__}", render_html_report(Report(Path(tmp))))

    def test_html_escaping(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Report(Path(tmp))
            report.add("WARN", "<script>", '<img src=x onerror=alert(1)>', 'Use "&"')
            html = render_html_report(report)
            self.assertIn("&lt;script&gt;", html)
            self.assertNotIn("<script>", html)
            self.assertIn("&lt;img", html)

    def test_required_icon_assets(self):
        self.assertTrue((ROOT/"assets"/"repomedic_logo.ico").stat().st_size > 100)
        self.assertTrue((ROOT/"assets"/"repomedic_logo.png").stat().st_size > 100)

    def test_build_dependencies_pinned(self):
        self.assertIn("pyinstaller==", (ROOT/"requirements-build.txt").read_text(encoding="utf-8"))

    def test_build_script_uses_clean_dir(self):
        source = (ROOT/"scripts"/"build_windows.ps1").read_text(encoding="utf-8")
        self.assertIn("--onedir", source)
        self.assertIn("--windowed", source)
        self.assertIn("--icon", source)
        self.assertIn("--add-data", source)
        self.assertIn("--clean", source)

    def test_packaging_includes_checksum(self):
        source = (ROOT/"scripts"/"package_windows.ps1").read_text(encoding="utf-8")
        self.assertIn("Get-FileHash", source)
        self.assertIn("SHA256SUMS.txt", source)
        self.assertIn("Compress-Archive", source)

    def test_ci_uses_pinned_actions(self):
        workflow = (ROOT/".github/workflows/tests.yml").read_text(encoding="utf-8")
        uses = re.findall(r"^\s*[- ]*uses:\s*([^\s#]+)", workflow, re.M)
        self.assertGreaterEqual(len(uses), 5)
        for action in uses:
            self.assertRegex(action, r"^[\w-]+/[\w-]+@[0-9a-f]{40}$")

    def test_ci_release_guard(self):
        workflow = (ROOT/".github/workflows/tests.yml").read_text(encoding="utf-8")
        self.assertIn("needs: windows-build", workflow)
        self.assertIn("--verify-tag", workflow)
        self.assertIn("scripts/check_release.py --tag", workflow)

    def test_manual_release_checklist_present(self):
        self.assertIn("clean Windows", (ROOT/"docs/RELEASE_CHECKLIST.md").read_text(encoding="utf-8"))

    def test_cli_version(self):
        # Windows often defaults to cp1251 when stdout is captured by a pipe.
        # Request UTF-8 from the child interpreter to match our decoder.
        result = subprocess.run([sys.executable, str(ROOT/"cli.py"), "--help"],
                                capture_output=True, text=True, encoding="utf-8",
                                env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        self.assertEqual(result.returncode, 0)
        self.assertIn("v1.0.0", result.stdout)

    def test_github_url_restricts_protocol(self):
        from github_downloader import DownloadError
        with self.assertRaises(DownloadError):
            parse_github_url("http://github.com/a/b")


if __name__ == "__main__":
    unittest.main()

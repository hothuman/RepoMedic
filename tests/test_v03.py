import io
import json
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path

from diagnostics import Report, analyze_project
from git_diagnostics import _public_remote
from github_downloader import DownloadError, parse_github_url, safe_extract
from node_diagnostics import _range_test


class NodeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "README.md").write_text("# test")
        (self.root / "LICENSE").write_text("MIT")
        (self.root / ".gitignore").write_text("node_modules/\n")

    def _package(self, **kwargs):
        (self.root / "package.json").write_text(json.dumps(kwargs), encoding="utf-8")

    def test_node_only_skips_python_virtualenv_warning(self):
        self._package(name="app", dependencies={"leftpad": "^1.2.0"})
        report = analyze_project(self.root)
        self.assertFalse(any("venv" in f.message for f in report.findings))
        self.assertTrue(any("node_modules отсутствует" in f.message for f in report.findings))
        self.assertTrue(any("Node.js" in f.message for f in report.findings))

    def test_installed_node_package_and_wrong_version(self):
        self._package(dependencies={"example": "^2.0.0", "other": ">=1.0.0"})
        (self.root / "package-lock.json").write_text("{}")
        for name, version in (("example", "1.5.0"), ("other", "1.2.0")):
            path = self.root / "node_modules" / name
            path.mkdir(parents=True)
            (path / "package.json").write_text(json.dumps({"version": version}))
        report = analyze_project(self.root)
        self.assertTrue(any(f.level == "ERROR" and "example:" in f.message for f in report.findings))
        self.assertTrue(any(f.level == "OK" and "other:" in f.message for f in report.findings))

    def test_invalid_manifest_error(self):
        (self.root / "package.json").write_text("{ invalid")
        report = analyze_project(self.root)
        self.assertTrue(any(f.level == "ERROR" and "package.json" in f.message for f in report.findings))

    def test_unknown_node_range_is_skip_not_error(self):
        self._package(dependencies={"example": "workspace:*"})
        path = self.root / "node_modules" / "example"
        path.mkdir(parents=True)
        (path / "package.json").write_text('{"version":"1.2.0"}')
        report = analyze_project(self.root)
        self.assertTrue(any(f.level == "SKIP" and "example:" in f.message for f in report.findings))

    def test_score_json(self):
        report = Report(self.root)
        report.add("OK", "X", "good")
        report.add("WARN", "X", "warning", "fix this")
        report.add("ERROR", "Y", "bad")
        self.assertEqual(report.score(), 75)
        payload = json.loads(report.to_json())
        self.assertEqual(payload["score"], 75)
        self.assertEqual(payload["findings"][1]["advice"], "fix this")
        self.assertEqual(payload["version"], "1.0.0")
        self.assertIn("Совет: fix this", report.to_text())

    def test_npm_range_subset(self):
        self.assertTrue(_range_test("1.9.0", "^1.2.0"))
        self.assertFalse(_range_test("2.0.0", "^1.2.0"))
        self.assertTrue(_range_test("0.2.3", "^0.2.1"))
        self.assertFalse(_range_test("0.4.0", "^0.2.1"))
        self.assertTrue(_range_test("1.2.7", "~1.2.0"))
        self.assertFalse(_range_test("1.3.0", "~1.2.0"))
        self.assertTrue(_range_test("2.4.0", ">=2.0.0 <3.0.0"))
        self.assertIsNone(_range_test("2.4.0", "^1 || ^2"))
        self.assertIsNone(_range_test("2.4.0", "2.4"))


class GitTests(unittest.TestCase):
    def test_git_remote_with_password_not_exposed(self):
        display, is_github = _public_remote("https://user:secret@github.com/example/repo.git")
        self.assertTrue(is_github)
        self.assertEqual(display, "GitHub: example/repo")
        self.assertNotIn("secret", display)

    def test_git_local_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            git = root / ".git"
            git.mkdir()
            (git / "HEAD").write_text("ref: refs/heads/main\n")
            (git / "config").write_text('[core]\nrepositoryformatversion = 0\n[remote "origin"]\nurl = https://github.com/owner/repo.git\n')
            report = analyze_project(root)
            self.assertTrue(any("GitHub: owner/repo" in f.message for f in report.findings))
            self.assertTrue(any("Ветка: main" in f.message for f in report.findings))


class GitHubArchiveTests(unittest.TestCase):
    def test_url_validation(self):
        self.assertEqual(parse_github_url("https://github.com/alice/repo.git"), ("alice", "repo"))
        for url in ("http://github.com/a/b", "https://evil.com/a/b", "https://github.com/a/b/tree/main",
                    "https://user:pass@github.com/a/b", "https://github.com/a/b?token=abc"):
            with self.subTest(url=url), self.assertRaises(DownloadError):
                parse_github_url(url)

    def _archive(self, entries):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as archive:
            for path, data in entries:
                archive.writestr(path, data)
        buf.seek(0)
        return zipfile.ZipFile(buf)

    def test_safe_zip_extract(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            with self._archive([("root-main/README.md", "hello"), ("root-main/src/app.js", "pass")]) as archive:
                folder = safe_extract(archive, target)
            self.assertEqual((folder / "README.md").read_text(), "hello")
            self.assertTrue((folder / "src" / "app.js").exists())

    def test_reject_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            with self._archive([("root-main/../../escaped.txt", "oops")]) as archive:
                with self.assertRaises(DownloadError):
                    safe_extract(archive, Path(temp))

    def test_reject_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as archive:
                info = zipfile.ZipInfo("root-main/link")
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(info, "../../file")
            buf.seek(0)
            with zipfile.ZipFile(buf) as archive:
                with self.assertRaises(DownloadError):
                    safe_extract(archive, Path(temp))


if __name__ == "__main__":
    unittest.main()

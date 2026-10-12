import tempfile
import unittest
from pathlib import Path

from diagnostics import analyze_project


class ReportTests(unittest.TestCase):
    def test_missing_files_gives_warnings(self):
        with tempfile.TemporaryDirectory() as temp:
            report = analyze_project(Path(temp))
            self.assertGreaterEqual(report.counts()["WARN"], 1)
            self.assertIn("Код проекта не выполнялся", report.to_text())

    def test_installed_and_incompatible_dependency(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "requirements.txt").write_text("example-tool>=2.0\n", encoding="utf-8")
            env = root / ".venv"
            site = env / "Lib" / "site-packages"
            metadata = site / "example_tool-1.5.dist-info"
            metadata.mkdir(parents=True)
            (env / "pyvenv.cfg").write_text("version = 3.15.0\n", encoding="utf-8")
            (metadata / "METADATA").write_text("Metadata-Version: 2.1\nName: example-tool\nVersion: 1.5\n", encoding="utf-8")
            report = analyze_project(root)
            self.assertTrue(any(f.level == "ERROR" and "example-tool" in f.message
                                for f in report.findings))

    def test_valid_dependency(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "requirements.txt").write_text("example-tool>=1.0\n", encoding="utf-8")
            env = root / ".venv"
            metadata = env / "Lib" / "site-packages" / "example_tool-1.5.dist-info"
            metadata.mkdir(parents=True)
            (env / "pyvenv.cfg").write_text("version = 3.15.0\n", encoding="utf-8")
            (metadata / "METADATA").write_text("Metadata-Version: 2.1\nName: example-tool\nVersion: 1.5\n", encoding="utf-8")
            report = analyze_project(root)
            self.assertTrue(any(f.level == "OK" and "example-tool" in f.message
                                for f in report.findings))

    def test_included_requirements(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "requirements.txt").write_text("-r more.txt\n", encoding="utf-8")
            (root / "more.txt").write_text("sample>=1\n", encoding="utf-8")
            report = analyze_project(root)
            self.assertTrue(any("Объявлено записей зависимостей: 1" in f.message
                                for f in report.findings))


if __name__ == "__main__":
    unittest.main()

"""Cross-platform regression tests for declarative Python manager support."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from diagnostics import analyze_project
from manifest_checks import _poetry_constraint


class TestManifestV06(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / "README.md").write_text("# App", encoding="utf-8")
        (self.root / "LICENSE").write_text("MIT", encoding="utf-8")
        (self.root / ".gitignore").write_text(".venv/\n", encoding="utf-8")

    def scan(self, source="github"):
        return analyze_project(self.root, source=source)

    def matching(self, report, needle, section=None, level=None):
        return [f for f in report.findings if needle in f.message
                and (section is None or f.section == section)
                and (level is None or f.level == level)]

    def test_poetry_caret_range_detected(self):
        (self.root / "pyproject.toml").write_text('[tool.poetry.dependencies]\npython = ">=3.11"\nrequests = "^2.31"\n', encoding="utf-8")
        report = self.scan()
        self.assertTrue(self.matching(report, "Poetry: распознано обязательных зависимостей: 1", level="OK"))
        self.assertTrue(self.matching(report, "Объявлено записей зависимостей: 1"))

    def test_poetry_optional_not_required(self):
        (self.root / "pyproject.toml").write_text('[tool.poetry.dependencies]\nrequests = {version="^2.0", optional=true}\n', encoding="utf-8")
        report = self.scan()
        self.assertTrue(self.matching(report, "необязательных зависимостей: 1"))
        self.assertFalse(self.matching(report, "Не установлен: requests"))

    def test_poetry_pep621_override_no_duplicate(self):
        (self.root / "pyproject.toml").write_text('[project]\ndependencies = ["sample==1.0"]\n'
             '[tool.poetry.dependencies]\nsample = "^2.0"\n', encoding="utf-8")
        report = self.scan()
        self.assertTrue(self.matching(report, "используются зависимости [project.dependencies]"))
        self.assertFalse(self.matching(report, "несовместимые объявленные ограничения"))
        self.assertTrue(self.matching(report, "Объявлено записей зависимостей: 1"))

    def test_poetry_invalid_table_warns(self):
        (self.root / "pyproject.toml").write_text('[tool.poetry]\ndependencies = "invalid"\n', encoding="utf-8")
        report = self.scan()
        self.assertTrue(self.matching(report, "dependencies должен", level="WARN"))

    def test_poetry_unknown_complex_constraint_skips(self):
        (self.root / "pyproject.toml").write_text('[tool.poetry.dependencies]\ndemo = "^1 || ^2"\n', encoding="utf-8")
        report = self.scan()
        self.assertTrue(self.matching(report, "сложных/неподдерживаемых записей", level="SKIP"))
        self.assertFalse(self.matching(report, "Не установлен: demo"))

    def test_poetry_git_dependency_skipped(self):
        (self.root / "pyproject.toml").write_text('[tool.poetry.dependencies]\ndemo = {git = "https://example.invalid/xxx.git"}\n', encoding="utf-8")
        report = self.scan()
        self.assertTrue(self.matching(report, "пропущено: 1", level="SKIP"))

    def test_poetry_version_marker_supported(self):
        (self.root / "pyproject.toml").write_text(
            '[tool.poetry.dependencies]\ndemo = {version="^1.0", markers="python_version < \'3.8\'"}\n',
            encoding="utf-8")
        report = self.scan()
        self.assertTrue(self.matching(report, "Объявлено записей зависимостей: 1"))
        self.assertFalse(self.matching(report, "неверное условие", level="WARN"))

    def test_poetry_range_exact(self):
        self.assertEqual(_poetry_constraint("1.2.3"), "==1.2.3")
        self.assertEqual(_poetry_constraint("^0.0.4"), ">=0.0.4,<0.0.5")
        self.assertEqual(_poetry_constraint("^0"), ">=0,<1.0.0")
        self.assertEqual(_poetry_constraint("^0.0"), ">=0.0,<0.1.0")
        self.assertEqual(_poetry_constraint("~1.2"), ">=1.2,<1.3.0")
        self.assertEqual(_poetry_constraint("~1"), ">=1,<2.0.0")
        self.assertEqual(_poetry_constraint("1.*"), "==1.*")

    def test_extreme_poetry_version_is_skipped_without_crash(self):
        (self.root / "pyproject.toml").write_text(
            '[tool.poetry.dependencies]\ndemo = "^' + '9' * 6000 + '"\n', encoding="utf-8")
        report = self.scan()
        self.assertTrue(self.matching(report, "неподдерживаемых записей", level="SKIP"))

    def test_pipfile_and_poetry_sources_both_recognized(self):
        (self.root / "Pipfile").write_text('[packages]\nclick="==8.0"\n', encoding="utf-8")
        (self.root / "pyproject.toml").write_text('[tool.poetry.dependencies]\nrequests="^2.31"\n', encoding="utf-8")
        report = self.scan()
        self.assertTrue(self.matching(report, "Объявлено записей зависимостей: 2"))

    def test_poetry_range_unknown(self):
        self.assertIsNone(_poetry_constraint("^not-a-version"))
        self.assertIsNone(_poetry_constraint("^1 || ^2"))

    def test_pipfile_packages_supported(self):
        (self.root / "Pipfile").write_text('[packages]\nrequests = "==2.32"\nclick = "*"\n', encoding="utf-8")
        report = self.scan()
        self.assertTrue(self.matching(report, "Pipenv: распознано обязательных зависимостей: 2", level="OK"))
        self.assertTrue(self.matching(report, "Объявлено записей зависимостей: 2"))

    def test_pipfile_dev_dependencies_optional(self):
        (self.root / "Pipfile").write_text('[packages]\nrequests="*"\n[dev-packages]\npytest="==8"\n', encoding="utf-8")
        report = self.scan()
        self.assertTrue(self.matching(report, "dev-пакетов: 1", level="INFO"))
        self.assertTrue(self.matching(report, "Объявлено записей зависимостей: 1"))
        self.assertFalse(self.matching(report, "Не установлен: pytest"))

    def test_pipfile_git_dependency_skipped(self):
        (self.root / "Pipfile").write_text('[packages]\ndemo = {git="https://example.invalid/foo.git"}\n', encoding="utf-8")
        report = self.scan()
        self.assertTrue(self.matching(report, "нестандартных записей пропущено: 1", level="SKIP"))

    def test_pipfile_invalid_format_warns(self):
        (self.root / "Pipfile").write_text('[packages]\nhello = ["1"]\n', encoding="utf-8")
        report = self.scan()
        self.assertTrue(self.matching(report, "нестандартных записей пропущено", level="SKIP"))

    def test_pipfile_lock_notice(self):
        (self.root / "Pipfile").write_text('[packages]\ndemo = "==1"\n', encoding="utf-8")
        (self.root / "Pipfile.lock").write_text("{}", encoding="utf-8")
        report = self.scan()
        self.assertTrue(self.matching(report, "Обнаружен Pipfile.lock", level="OK"))

    def test_setup_cfg_requires(self):
        (self.root / "setup.cfg").write_text('[options]\ninstall_requires =\n    requests>=2\n    click==8.0\n', encoding="utf-8")
        report = self.scan()
        self.assertTrue(self.matching(report, "setuptools setup.cfg: обязательных зависимостей: 2", level="OK"))

    def test_setup_cfg_extras_not_required(self):
        (self.root / "setup.cfg").write_text('[options]\ninstall_requires =\n    requests>=2\n'
            '[options.extras_require]\ntest =\n    pytest>=7\n', encoding="utf-8")
        report = self.scan()
        self.assertTrue(self.matching(report, "extras_require не включаются", level="INFO"))
        self.assertTrue(self.matching(report, "Объявлено записей зависимостей: 1"))

    def test_setup_cfg_bad_spec_warns(self):
        (self.root / "setup.cfg").write_text('[options]\ninstall_requires =\n    bad!!!\n', encoding="utf-8")
        report = self.scan()
        self.assertTrue(self.matching(report, "некорректная запись install_requires", level="WARN"))

    def test_setup_cfg_broken_config_warns_not_crashes(self):
        (self.root / "setup.cfg").write_text('[options\ninstall_requires = bad\n', encoding="utf-8")
        report = self.scan()
        self.assertTrue(self.matching(report, "не удалось прочитать", level="WARN"))

    def test_corrupted_pipfile_warns_not_crashes(self):
        (self.root / "Pipfile").write_text('[[broken\n', encoding="utf-8")
        report = self.scan()
        self.assertTrue(self.matching(report, "нельзя прочитать манифест", level="WARN"))

    def test_large_pipfile_bounded(self):
        (self.root / "Pipfile").write_bytes(b"# filler\n" * 300000)
        report = self.scan()
        self.assertTrue(self.matching(report, "нельзя прочитать манифест", level="WARN"))

    def test_pipfile_no_python_venv_github_is_skip(self):
        (self.root / "Pipfile").write_text('[packages]\nrequests = "==2.32"\n', encoding="utf-8")
        report = self.scan()
        self.assertTrue(self.matching(report, "GitHub ZIP не содержит", level="SKIP"))
        self.assertFalse(self.matching(report, "В корне не найдено .venv", level="WARN"))

    def test_alternative_manifests_check_installed_metadata(self):
        (self.root / "Pipfile").write_text('[packages]\nexample-tool = ">=2"\n', encoding="utf-8")
        meta = self.root / ".venv" / "Lib" / "site-packages" / "example_tool-1.0.dist-info"
        meta.mkdir(parents=True)
        (self.root / ".venv" / "pyvenv.cfg").write_text("version = 3.13.0\n", encoding="utf-8")
        (meta / "METADATA").write_text("Metadata-Version: 2.1\nName: example-tool\nVersion: 1.0\n", encoding="utf-8")
        report = self.scan(source="local")
        self.assertTrue(self.matching(report, "example-tool: установлена 1.0", level="ERROR"))

    def test_managers_do_not_run_project_code(self):
        marker = self.root / "code-ran.txt"
        (self.root / "setup.py").write_text(f'from pathlib import Path\nPath({str(marker)!r}).write_text("oops")\n', encoding="utf-8")
        (self.root / "setup.cfg").write_text('[options]\ninstall_requires =\n    requests>=2\n', encoding="utf-8")
        self.scan()
        self.assertFalse(marker.exists())

    def test_json_version_is_current(self):
        (self.root / "Pipfile").write_text('[packages]\nrequests = "*"\n', encoding="utf-8")
        data = json.loads(self.scan().to_json())
        self.assertEqual(data["version"], "1.0.0")
        self.assertTrue(any(f["section"] == "Менеджеры Python" for f in data["findings"]))

    def test_conflicting_requirements_and_pipfile_detected(self):
        (self.root / "requirements.txt").write_text('example-tool==1.0\n', encoding="utf-8")
        (self.root / "Pipfile").write_text('[packages]\nexample-tool = "==2.0"\n', encoding="utf-8")
        report = self.scan()
        self.assertTrue(self.matching(report, "несовместимые объявленные ограничения", section="Конфликты зависимостей", level="ERROR"))

    def test_lock_files_are_not_executed_or_opened(self):
        (self.root / "Pipfile").write_text('[packages]\nclick = "*"\n', encoding="utf-8")
        (self.root / "Pipfile.lock").write_text('not even valid JSON', encoding="utf-8")
        report = self.scan()
        self.assertTrue(self.matching(report, "содержимое не анализируется", level="OK"))


if __name__ == "__main__":
    unittest.main()

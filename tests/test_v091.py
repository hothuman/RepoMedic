"""Cross-platform regression tests for RepoMedic 0.9.1 Visual Polish.

The GUI smoke test is intentionally a separate Windows step; these tests do
not require a display server or Qt to run.
"""
import json
import tempfile
import unittest
from pathlib import Path

from diagnostics import Report
from html_report import render_html_report
from i18n import LANGUAGES, RU, translate, translate_navigation
from theme import COLORS, stylesheet
from ui_state import clear_history, load_settings, save_settings


class LanguageTests(unittest.TestCase):
    def test_supported_languages(self):
        self.assertEqual(LANGUAGES, ("en", "ru"))

    def test_russian_navigation(self):
        self.assertEqual(translate("Dashboard", "ru"), "Главная")
        self.assertEqual(translate("History", "ru"), "История")

    def test_prefixed_navigation_buttons_ru(self):
        for prefix, label in (("⌂", "Dashboard"), ("◉", "Scanner"),
                              ("◷", "History"), ("▤", "Reports"), ("⚙", "Settings")):
            self.assertEqual(translate_navigation(f"{prefix}   {label}", "ru"),
                             f"{prefix}   {translate(label, 'ru')}")

    def test_prefixed_navigation_buttons_en_and_untrusted(self):
        self.assertEqual(translate_navigation("⌂   Dashboard", "en"), "⌂   Dashboard")
        self.assertEqual(translate_navigation("●   unexpected user text", "ru"),
                         "●   unexpected user text")

    def test_russian_settings(self):
        self.assertEqual(translate("Settings", "ru"), "Настройки")
        self.assertEqual(translate("Dark", "ru"), "Тёмная")

    def test_english_unchanged(self):
        for value in ("Dashboard", "Scanner", "Reports", "Theme"):
            self.assertEqual(translate(value, "en"), value)

    def test_invalid_locale_falls_back_to_english(self):
        self.assertEqual(translate("Scanner", "zz"), "Scanner")

    def test_untrusted_project_string_not_changed(self):
        user_text = "docker/Dockerfile.dev <script>"
        self.assertEqual(translate(user_text, "ru"), user_text)

    def test_only_nonempty_ui_keys(self):
        self.assertTrue(all(k and v for k, v in RU.items()))

    def test_translation_for_all_tabs(self):
        for name in ("Dashboard", "Scanner", "History", "Reports", "Settings"):
            self.assertNotEqual(translate(name, "ru"), name)

    def test_critical_actions_translated(self):
        for name in ("Run a scan to see actionable recommendations.",
                     "Export report", "Choose folder", "Clear history"):
            self.assertNotEqual(translate(name, "ru"), name)


class PersistedLanguageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_old_settings_default_to_english(self):
        (self.root / "settings.json").write_text(
            '{"theme":"light","save_history":false}', encoding="utf-8")
        settings = load_settings(self.root)
        self.assertEqual(settings["language"], "en")
        self.assertEqual(settings["theme"], "light")
        self.assertFalse(settings["save_history"])

    def test_ru_survives_restart(self):
        save_settings(self.root, {"theme":"dark", "save_history":True, "language":"ru"})
        self.assertEqual(load_settings(self.root)["language"], "ru")

    def test_en_survives_restart(self):
        save_settings(self.root, {"theme":"light", "save_history":True, "language":"en"})
        self.assertEqual(load_settings(self.root)["language"], "en")

    def test_invalid_language_ignored(self):
        save_settings(self.root, {"language":"unknown"})
        self.assertEqual(load_settings(self.root)["language"], "en")

    def test_invalid_language_in_user_file_ignored(self):
        (self.root / "settings.json").write_text('{"language":"es"}', encoding="utf-8")
        self.assertEqual(load_settings(self.root)["language"], "en")

    def test_history_cleanup_doesnt_delete_language(self):
        save_settings(self.root, {"theme":"dark", "save_history":True, "language":"ru"})
        clear_history(self.root)
        self.assertEqual(load_settings(self.root)["language"], "ru")


class CompatibilityTests(unittest.TestCase):
    def test_report_versions_are_consistent(self):
        report = Report(Path("my_project"))
        self.assertEqual(json.loads(report.to_json())["version"], "1.0.0")
        self.assertIn("REPOMEDIC 1.0.0", report.to_text())
        self.assertIn("Версия 1.0.0", render_html_report(report))

    def test_dark_light_maintain_brand_accent(self):
        for theme in ("dark", "light"):
            self.assertIn(COLORS[theme]["accent"], stylesheet(theme))
            self.assertIn(COLORS[theme]["red"], stylesheet(theme))

    def test_logo_assets_present(self):
        root = Path(__file__).resolve().parents[1]
        for extension in ("png", "ico"):
            self.assertTrue((root / "assets" / f"repomedic_logo.{extension}").is_file())


if __name__ == "__main__":
    unittest.main()

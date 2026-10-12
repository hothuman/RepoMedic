"""RepoMedic v0.9 history, theme and version regression tests (no GUI needed)."""
import json
import tempfile
import unittest
from pathlib import Path

from diagnostics import Report
from html_report import render_html_report
from theme import COLORS, stylesheet
from ui_state import (
    MAX_HISTORY, add_to_history, clear_history, load_history, load_settings,
    restore_report, save_history, save_settings, snapshot,
)


class StateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.report = Report(self.root)
        self.report.add("OK", "Python", "Syntax OK")
        self.report.add("WARN", "Docker", "No USER", "Specify a non-root user")

    def test_default_settings(self):
        self.assertEqual(load_settings(self.root)["theme"], "dark")
        self.assertTrue(load_settings(self.root)["save_history"])

    def test_settings_round_trip(self):
        save_settings(self.root, {"theme": "light", "save_history": False})
        self.assertEqual(load_settings(self.root), {"theme": "light", "save_history": False, "language": "en"})

    def test_settings_ignores_unknown_theme(self):
        (self.root / "settings.json").write_text('{"theme":"purple","save_history":"yes"}')
        self.assertEqual(load_settings(self.root), {"theme": "dark", "save_history": True, "language": "en"})

    def test_settings_corrupt_json(self):
        (self.root / "settings.json").write_text("not json")
        self.assertEqual(load_settings(self.root)["theme"], "dark")

    def test_history_round_trip(self):
        first = snapshot(self.report, 0.231, "repo-test")
        save_history(self.root, [first])
        stored = load_history(self.root)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["label"], "repo-test")
        self.assertEqual(stored[0]["counts"]["WARN"], 1)

    def test_restore_report(self):
        restored = restore_report(snapshot(self.report, 2.0))
        self.assertEqual(restored.score(), self.report.score())
        self.assertEqual(restored.findings[1].advice, "Specify a non-root user")

    def test_history_is_bounded(self):
        entries = [snapshot(self.report, 0.1, str(i)) for i in range(75)]
        save_history(self.root, entries)
        self.assertEqual(len(load_history(self.root)), MAX_HISTORY)

    def test_prepend_history_is_bounded(self):
        entries = [{"label": str(i)} for i in range(80)]
        data = add_to_history(entries, {"label": "new"})
        self.assertEqual(len(data), MAX_HISTORY)
        self.assertEqual(data[0]["label"], "new")

    def test_clear_history_leaves_settings(self):
        save_settings(self.root, {"theme": "light", "save_history": True})
        save_history(self.root, [snapshot(self.report, 0.1)])
        clear_history(self.root)
        self.assertEqual(load_history(self.root), [])
        self.assertEqual(load_settings(self.root)["theme"], "light")

    def test_bad_history_gracefully_ignored(self):
        (self.root / "history.json").write_text('"not-list"')
        self.assertEqual(load_history(self.root), [])

    def test_missing_history_does_not_error(self):
        self.assertEqual(load_history(self.root), [])
        clear_history(self.root)

    def test_limit_history_items(self):
        raw = snapshot(self.report, 1.0, "r")
        with (self.root / "history.json").open("w", encoding="utf-8") as stream:
            json.dump([raw] * 100, stream)
        self.assertEqual(len(load_history(self.root)), MAX_HISTORY)

    def test_snapshot_duration_nonnegative(self):
        self.assertEqual(snapshot(self.report, -7)["duration_seconds"], 0)

    def test_restore_history_includes_github_source(self):
        self.report.source = "github"
        self.assertEqual(restore_report(snapshot(self.report, 1)).source, "github")

    def test_report_disclosure_is_local(self):
        save_history(self.root, [snapshot(self.report, 1)])
        text = (self.root / "history.json").read_text(encoding="utf-8")
        self.assertIn("Syntax OK", text)
        self.assertIn("Docker", text)


class BrandTests(unittest.TestCase):
    def test_dark_theme(self):
        self.assertIn(COLORS["dark"]["accent"], stylesheet("dark"))

    def test_light_theme(self):
        self.assertIn(COLORS["light"]["bg"], stylesheet("light"))

    def test_report_version(self):
        report = Report(Path("."))
        self.assertEqual(json.loads(report.to_json())["version"], "1.0.0")
        self.assertIn("REPOMEDIC 1.0.0", report.to_text())
        self.assertIn("Версия 1.0.0", render_html_report(report))

    def test_html_escapes_untrusted_project_names(self):
        report = Report(Path("bad&name"))
        report.add("WARN", "Test", "<script>x</script>")
        html = render_html_report(report)
        self.assertNotIn("<script>x</script>", html)
        self.assertIn("&lt;script&gt;", html)


if __name__ == "__main__":
    unittest.main()

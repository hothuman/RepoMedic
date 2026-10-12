"""Windows manual smoke test: launches temporary GUI and checks theme and localization.

Run from project root with: .\\.venv\\Scripts\\python.exe scripts\\smoke_gui.py
No project folders are touched or scanned.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication
from main import MainWindow

app = QApplication.instance() or QApplication([])
app.setStyle("Fusion")
with tempfile.TemporaryDirectory() as temp:
    window = MainWindow(storage_dir=Path(temp))
    window.resize(1050, 740)
    window.show()
    app.processEvents()
    assert window._responsive_narrow is True
    # Using an isolated storage_dir keeps this test independent of the
    # language/theme selected in a user's real RepoMedic profile.
    assert window.settings["language"] == "en", "Unexpected default language"
    window._navigate(4)
    window.language_select.setCurrentIndex(1)
    app.processEvents()
    assert "Главная" in window.nav_buttons[0].text(), "RU navigation failed"
    assert "Настройки" in window.nav_buttons[4].text(), "RU settings navigation failed"
    window.language_select.setCurrentIndex(0)
    app.processEvents()
    assert "Dashboard" in window.nav_buttons[0].text(), "EN navigation restoration failed"
    window.language_select.setCurrentIndex(1)
    app.processEvents()
    assert "Главная" in window.nav_buttons[0].text(), "RU navigation reselect failed"
    window.theme_select.setCurrentIndex(1)
    app.processEvents()
    assert window.settings["theme"] == "light", "Theme switch failed"
    assert window.settings["language"] == "ru", "Locale not saved"
    window.resize(1550, 900)
    app.processEvents()
    assert window._responsive_narrow == (window.width() - 244 < 1050), "Responsive layout mismatch"
    window.close()
print("RepoMedic v1.0 GUI smoke test: OK")

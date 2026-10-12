"""RepoMedic v1.0 Developer Pro — localized, responsive desktop UI."""
from __future__ import annotations

import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import (QObject, QRectF, QSize, Qt, QThread, Signal, Slot,
                            QPropertyAnimation, QEasingCurve)
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPen, QPixmap, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QAbstractButton, QBoxLayout, QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout,
    QGraphicsOpacityEffect,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSizePolicy,
    QStackedWidget, QTableWidget, QTableWidgetItem, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from diagnostics import Report, analyze_project
from version import __version__, DISPLAY_VERSION
from i18n import translate, translate_navigation
from github_downloader import DownloadError, download_public_repo, parse_github_url
from html_report import render_html_report
from report_io import atomic_save_text
from theme import COLORS, stylesheet
from ui_state import (
    add_to_history, clear_history, default_storage_dir, load_history,
    load_settings, restore_report, save_history, save_settings, snapshot,
)

VERSION = __version__


def asset_path(filename: str) -> Path:
    # PyInstaller --onedir includes assets below its resource directory.
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / "assets" / filename


def label(text: str, style: str = "", *, wrap: bool = False) -> QLabel:
    item = QLabel(text)
    # Finding text and project names are untrusted: never interpret as HTML.
    item.setTextFormat(Qt.TextFormat.PlainText)
    if style:
        item.setObjectName(style)
    item.setWordWrap(wrap)
    return item


def button(text: str, callback, role: str = "") -> QPushButton:
    item = QPushButton(text)
    if role:
        item.setObjectName(role)
    item.clicked.connect(callback)
    return item


def card(title: str = "", role: str = "Card") -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName(role)
    box = QVBoxLayout(frame)
    box.setContentsMargins(18, 18, 18, 18)
    box.setSpacing(12)
    if title:
        box.addWidget(label(title, "CardTitle"))
    return frame, box


def clear_layout(layout: QVBoxLayout | QHBoxLayout | QGridLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            clear_layout(item.layout())


def time_label(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds * 1000:.0f} ms"
    if seconds < 60:
        return f"{seconds:.1f} s"
    minutes, remain = divmod(round(seconds), 60)
    return f"{minutes}m {remain:02d}s"


def fmt_date(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        return dt.astimezone().strftime("%d.%m.%Y  %H:%M")
    except (ValueError, TypeError):
        return "—"


def _cell(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


class ScoreGauge(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.value: int | None = None
        self.theme = "dark"
        self.setMinimumSize(116, 116)
        self.setMaximumSize(145, 145)

    def set_score(self, value: int | None) -> None:
        self.value = value
        self.update()

    def paintEvent(self, _event) -> None:
        color = COLORS[self.theme]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height()) - 22
        bounds = QRectF((self.width() - side)/2, (self.height() - side)/2, side, side)
        painter.setPen(QPen(QColor(color["track"]), 12, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(bounds, 0, 360*16)
        if self.value is not None:
            painter.setPen(QPen(QColor(color["accent"]), 12, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawArc(bounds, 90*16, -round(max(0, min(self.value, 100))*360*16/100))
        painter.setPen(QColor(color["text"]))
        painter.setFont(QFont("Segoe UI", 27, QFont.Weight.Bold))
        painter.drawText(self.rect().adjusted(0, -5, 0, 5), Qt.AlignmentFlag.AlignCenter,
                         str(self.value) if self.value is not None else "—")


class Sparkline(QWidget):
    """Display observed scan durations only; no fabricated demo data."""
    def __init__(self):
        super().__init__()
        self.values: list[float] = []
        self.theme = "dark"
        self.language = "en"
        self.setMinimumHeight(96)

    def set_values(self, values: list[float]):
        self.values = list(values)[-14:]
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        colors = COLORS[self.theme]
        if len(self.values) < 2:
            painter.setPen(QColor(colors["muted"]))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, translate("Trend available after 2 scans", self.language))
            return
        left, right, top, bottom = 8, self.width()-8, 10, self.height()-10
        low, high = min(self.values), max(self.values)
        spread = max(0.05, high-low)
        points = []
        for index, value in enumerate(self.values):
            x = left + index * (right-left)/max(1, len(self.values)-1)
            y = bottom - (value-low)/spread * (bottom-top)
            points.append((x, y))
        painter.setPen(QPen(QColor(colors["accent"]), 2))
        for a, b in zip(points, points[1:]):
            painter.drawLine(int(a[0]), int(a[1]), int(b[0]), int(b[1]))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(colors["accent"]))
        for x, y in points:
            painter.drawEllipse(int(x-3), int(y-3), 6, 6)


class ScanWorker(QObject):
    completed = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, folder: Path | None = None, github_url: str = "") -> None:
        super().__init__()
        self.folder = folder
        self.github_url = github_url

    @Slot()
    def run(self) -> None:
        temp: Path | None = None
        start = time.monotonic()
        try:
            if self.github_url:
                path, temp = download_public_repo(self.github_url)
                owner, repo = parse_github_url(self.github_url)
                name = f"{owner}/{repo}"
            else:
                if self.folder is None:
                    raise ValueError("Не выбрана папка")
                path = self.folder
                name = path.name
            report = analyze_project(path, source="github" if self.github_url else "local")
            self.completed.emit((report, temp, time.monotonic()-start, name))
        except (OSError, ValueError, DownloadError) as exc:
            if temp is not None:
                shutil.rmtree(temp, ignore_errors=True)
            self.failed.emit(str(exc))
        except Exception as exc:
            if temp is not None:
                shutil.rmtree(temp, ignore_errors=True)
            self.failed.emit(f"Неожиданная ошибка диагностики: {exc}")
        finally:
            self.finished.emit()


class MainWindow(QMainWindow):
    def __init__(self, storage_dir: Path | None = None) -> None:
        super().__init__()
        self.storage_dir = storage_dir or default_storage_dir()
        self.settings = load_settings(self.storage_dir)
        self.history = load_history(self.storage_dir)
        self.folder: Path | None = None
        self.report: Report | None = None
        self.report_label = ""
        self.scan_seconds = 0.0
        self._thread: QThread | None = None
        self._worker: ScanWorker | None = None
        self._temporary_folders: list[Path] = []
        self._loading_history = False
        self._last_scan_at: str | None = None
        self._page_animation = None
        self._animated_page = None
        self._responsive_narrow = None
        self.setWindowTitle(f"RepoMedic {DISPLAY_VERSION} · Developer Pro")
        self.resize(1460, 930)
        self.setMinimumSize(1000, 670)
        logo = asset_path("repomedic_logo.png")
        if logo.exists():
            self.setWindowIcon(QIcon(str(logo)))
        self._build_ui()
        self._register_shortcuts()
        self._translate_controls()
        self._apply_theme()
        self._update_ui()
        self._adjust_dashboard_layout()
        self.statusBar().showMessage(self._t("Ready · select a project to begin"))

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("AppRoot")
        self.setCentralWidget(root)
        root_layout = QHBoxLayout(root)
        root_layout.setSpacing(0)
        root_layout.setContentsMargins(0, 0, 0, 0)

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(244)
        sidebar_box = QVBoxLayout(sidebar)
        sidebar_box.setContentsMargins(16, 20, 16, 20)
        sidebar_box.setSpacing(10)
        brand = QHBoxLayout()
        brand.setSpacing(10)
        brand_logo = QLabel()
        logo_file = asset_path("repomedic_logo.png")
        if logo_file.exists():
            brand_logo.setPixmap(QPixmap(str(logo_file)).scaled(56, 56, Qt.AspectRatioMode.KeepAspectRatio,
                                                             Qt.TransformationMode.SmoothTransformation))
        brand_logo.setFixedSize(56, 56)
        brand.addWidget(brand_logo)
        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        brand_text.addWidget(label("RepoMedic", "BrandName"))
        brand_text.addWidget(label(f"{DISPLAY_VERSION}  ·  DEVELOPER PRO", "Detail"))
        brand.addLayout(brand_text, 1)
        sidebar_box.addLayout(brand)
        sidebar_box.addSpacing(28)
        self.nav_buttons = []
        navigation = [("⌂   Dashboard", 0), ("◉   Scanner", 1), ("◷   History", 2),
                      ("▤   Reports", 3), ("⚙   Settings", 4)]
        for name, index in navigation:
            nav = button(name, lambda _checked=False, i=index: self._navigate(i), "Nav")
            nav.setCheckable(True)
            nav.setMinimumHeight(42)
            self.nav_buttons.append(nav)
            sidebar_box.addWidget(nav)
        sidebar_box.addStretch()
        sidebar_about, sidebar_about_box = card("HEALTHY CODE.", "InnerPanel")
        sidebar_about_box.addWidget(label("STRONGER BUILDS.", "Detail", wrap=True))
        sidebar_about_box.addWidget(label("Local project diagnostics without executing untrusted project code.",
                                           "Detail", wrap=True))
        sidebar_box.addWidget(sidebar_about)
        sidebar_box.addWidget(label("Open Source · MIT License", "Hint"))
        root_layout.addWidget(sidebar)

        main_area = QWidget()
        main_layout = QVBoxLayout(main_area)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)
        header = QFrame()
        header.setObjectName("Topbar")
        top = QHBoxLayout(header)
        top.setContentsMargins(24, 13, 24, 13)
        top.setSpacing(12)
        self.project_path = label("No project selected", "Detail")
        self.project_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        top.addWidget(label("▣", "Accent"))
        self.project_path.setMinimumWidth(40)
        self.project_path.setWordWrap(True)
        top.addWidget(self.project_path, 1)
        self.header_choose = button("Open folder", self.choose_folder)
        top.addWidget(self.header_choose)
        self.header_status = label("● Ready", "Green")
        top.addWidget(self.header_status)
        self.header_busy = QProgressBar()
        self.header_busy.setFixedWidth(74)
        self.header_busy.setRange(0, 0)
        self.header_busy.hide()
        top.addWidget(self.header_busy)
        main_layout.addWidget(header)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_dashboard())
        self.pages.addWidget(self._build_scanner())
        self.pages.addWidget(self._build_history())
        self.pages.addWidget(self._build_reports())
        self.pages.addWidget(self._build_settings())
        main_layout.addWidget(self.pages, 1)
        root_layout.addWidget(main_area, 1)
        self._navigate(0)

    def _scroll_page(self):
        viewport = QScrollArea()
        viewport.setWidgetResizable(True)
        viewport.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 24, 24, 26)
        layout.setSpacing(16)
        viewport.setWidget(content)
        return viewport, layout

    def _build_dashboard(self):
        viewport, layout = self._scroll_page()
        hero, hero_box = card(role="Hero")
        headline = QHBoxLayout()
        left = QVBoxLayout()
        left.setSpacing(7)
        left.addWidget(label("PROJECT OVERVIEW", "MetricCaption"))
        self.hero_project = label("No project selected", "HeroTitle")
        left.addWidget(self.hero_project)
        self.hero_hint = label("Select a local folder or import from GitHub in Scanner.", "Detail", wrap=True)
        left.addWidget(self.hero_hint)
        headline.addLayout(left, 1)
        hero_run = button("▶  Run Diagnostics", self.scan_local, "Primary")
        self.hero_run = hero_run
        headline.addWidget(hero_run, alignment=Qt.AlignmentFlag.AlignVCenter)
        hero_box.addLayout(headline)
        layout.addWidget(hero)

        cards = QGridLayout()
        cards.setHorizontalSpacing(12)
        cards.setVerticalSpacing(12)
        self.metrics_grid = cards
        health, health_box = card("PROJECT HEALTH SCORE")
        health_row = QHBoxLayout()
        self.gauge = ScoreGauge()
        health_row.addWidget(self.gauge)
        health_text = QVBoxLayout()
        self.health_title = label("Not scanned", "CardTitle")
        health_desc = label("A heuristic based on detected warnings and errors — not a security audit.",
                            "Detail", wrap=True)
        health_text.addStretch()
        health_text.addWidget(self.health_title)
        health_text.addWidget(health_desc)
        health_text.addStretch()
        health_row.addLayout(health_text, 1)
        health_box.addLayout(health_row)
        self.health_card = health
        self.stat_cards = []
        cards.addWidget(health, 0, 0, 1, 2)
        self.metric_values = {}
        for caption in ("ERRORS", "WARNINGS", "PASSED CHECKS", "LAST SCAN"):
            frame, box = card()
            box.addWidget(label(caption, "MetricCaption"))
            item = label("—", "MetricNumber")
            item.setWordWrap(True)
            box.addWidget(item)
            box.addStretch()
            self.metric_values[caption] = item
            self.stat_cards.append(frame)
        layout.addLayout(cards)
        self.health_bar = QProgressBar()
        self.health_bar.setRange(0, 100)
        self.health_bar.setValue(0)
        self.health_bar.setTextVisible(False)
        layout.addWidget(self.health_bar)

        center = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        center.setSpacing(14)
        self.overview_layout = center
        diagnostic_card, diag_box = card("DIAGNOSTICS OVERVIEW")
        self.diagnostic_table = QTableWidget(0, 3)
        self.diagnostic_table.setHorizontalHeaderLabels(["Category", "Status", "Checks"])
        self._setup_table(self.diagnostic_table)
        self.diagnostic_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.diagnostic_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.diagnostic_table.cellDoubleClicked.connect(lambda r, _c: self._show_scanner_for_section(r))
        diag_box.addWidget(self.diagnostic_table)
        center.addWidget(diagnostic_card, 3)
        recommendations_card, rec_box = card("TOP RECOMMENDATIONS")
        self.recommendations_layout = QVBoxLayout()
        self.recommendations_layout.setSpacing(8)
        rec_box.addLayout(self.recommendations_layout)
        rec_box.addStretch()
        rec_box.addWidget(button("View all diagnostics  →", lambda: self._navigate(1), "Ghost"))
        center.addWidget(recommendations_card, 2)
        layout.addLayout(center, 3)

        bottom = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        bottom.setSpacing(14)
        self.bottom_layout = bottom
        history_card, history_box = card("RECENT SCANS")
        self.recent_table = QTableWidget(0, 3)
        self.recent_table.setHorizontalHeaderLabels(["Date", "Project", "Score"])
        self._setup_table(self.recent_table)
        self.recent_table.setMaximumHeight(210)
        self.recent_table.cellDoubleClicked.connect(lambda _r, _c: self._navigate(2))
        history_box.addWidget(self.recent_table)
        history_box.addWidget(button("Open scan history  →", lambda: self._navigate(2), "Ghost"))
        bottom.addWidget(history_card, 3)
        perf_card, perf_box = card("SCAN PERFORMANCE")
        self.duration_text = label("—", "MetricNumber")
        perf_box.addWidget(self.duration_text)
        perf_box.addWidget(label("Measured local scan duration; GitHub scans include download time.",
                                 "Detail", wrap=True))
        self.sparkline = Sparkline()
        perf_box.addWidget(self.sparkline)
        bottom.addWidget(perf_card, 2)
        layout.addLayout(bottom, 2)
        return viewport

    def _build_scanner(self):
        viewport, layout = self._scroll_page()
        layout.addWidget(label("Project Scanner", "SectionTitle"))
        layout.addWidget(label("Analyze Python, Node.js, Docker and GitHub configuration — read-only static checks.", "Detail"))
        source_card, sources = card("PROJECT SOURCE")
        local_row = QHBoxLayout()
        self.folder_label = label("Local project not selected", "Detail", wrap=True)
        local_row.addWidget(self.folder_label, 1)
        local_row.addWidget(button("Choose folder", self.choose_folder))
        sources.addLayout(local_row)
        remote_row = QHBoxLayout()
        self.github_input = QLineEdit()
        self.github_input.setPlaceholderText("https://github.com/owner/repository")
        self.github_input.returnPressed.connect(self.scan_github)
        remote_row.addWidget(self.github_input, 1)
        self.github_button = button("Import GitHub", self.scan_github)
        remote_row.addWidget(self.github_button)
        sources.addLayout(remote_row)
        row = QHBoxLayout()
        self.scan_button = button("▶  Scan selected folder", self.scan_local, "Primary")
        row.addWidget(self.scan_button)
        self.busy = QProgressBar()
        self.busy.setRange(0, 0)
        self.busy.setFixedWidth(150)
        self.busy.hide()
        row.addWidget(self.busy)
        row.addStretch()
        sources.addLayout(row)
        layout.addWidget(source_card)

        result_card, results = card("CHECK RESULTS")
        filters = QHBoxLayout()
        filters.addWidget(label("Severity", "Detail"))
        self.severity_filter = QComboBox()
        self.severity_filter.addItems(["All results", "Issues only", "Errors", "Warnings", "Passed"])
        self.severity_filter.currentIndexChanged.connect(self._apply_filter)
        filters.addWidget(self.severity_filter)
        filters.addStretch()
        self.scanner_count = label("No scan yet", "Detail")
        filters.addWidget(self.scanner_count)
        results.addLayout(filters)
        self.findings = QTreeWidget()
        self.findings.setHeaderLabels(["Status", "Section", "Diagnostic result"])
        self.findings.setAlternatingRowColors(True)
        self.findings.setRootIsDecorated(False)
        self.findings.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.findings.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.findings.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.findings.setMinimumHeight(290)
        self.findings.currentItemChanged.connect(self._show_finding_details)
        results.addWidget(self.findings, 1)
        self.finding_detail = label("Select a result to see its explanation and recommendations.",
                                    "Detail", wrap=True)
        results.addWidget(self.finding_detail)
        layout.addWidget(result_card, 1)
        layout.addWidget(label("🔒  Repository code is never executed. GitHub import downloads a bounded ZIP archive.",
                               "Hint", wrap=True))
        return viewport

    def _build_history(self):
        viewport, layout = self._scroll_page()
        h = QHBoxLayout()
        h.addWidget(label("Scan History", "SectionTitle"))
        h.addStretch()
        h.addWidget(button("Clear history", self._clear_history))
        layout.addLayout(h)
        layout.addWidget(label("Saved locally on this computer. Double-click a row to inspect an earlier report.",
                               "Detail", wrap=True))
        history_card, history_box = card("PREVIOUS DIAGNOSTICS")
        self.history_table = QTableWidget(0, 6)
        self.history_table.setHorizontalHeaderLabels(["Date", "Project", "Source", "Health", "Issues", "Time"])
        self._setup_table(self.history_table)
        self.history_table.setMinimumHeight(360)
        self.history_table.cellDoubleClicked.connect(self._load_history_row)
        history_box.addWidget(self.history_table)
        layout.addWidget(history_card)
        self.history_note = label("No saved scans yet.", "Detail")
        layout.addWidget(self.history_note)
        layout.addStretch()
        return viewport

    def _build_reports(self):
        viewport, layout = self._scroll_page()
        layout.addWidget(label("Reports", "SectionTitle"))
        layout.addWidget(label("Inspect the last selected scan and export a complete TXT, JSON or HTML report.",
                               "Detail", wrap=True))
        report_card, report_box = card("REPORT PREVIEW")
        controls = QHBoxLayout()
        self.report_caption = label("No report loaded", "Detail")
        controls.addWidget(self.report_caption, 1)
        self.export_format = QComboBox()
        self.export_format.addItems(["HTML", "JSON", "TXT"])
        controls.addWidget(self.export_format)
        self.export_button = button("Export report", self.export_report, "Primary")
        controls.addWidget(self.export_button)
        report_box.addLayout(controls)
        self.raw_output = QPlainTextEdit()
        self.raw_output.setReadOnly(True)
        self.raw_output.setPlaceholderText("Run a diagnosis to generate an exportable report.")
        self.raw_output.setMinimumHeight(460)
        report_box.addWidget(self.raw_output)
        layout.addWidget(report_card)
        layout.addWidget(label("HTML export is a self-contained local file. Existing export formats remain supported.",
                               "Hint", wrap=True))
        return viewport

    def _build_settings(self):
        viewport, layout = self._scroll_page()
        layout.addWidget(label("Settings", "SectionTitle"))
        layout.addWidget(label("Customize RepoMedic without affecting project files.", "Detail"))
        appearance, appearance_box = card("APPEARANCE")
        line = QHBoxLayout()
        line.addWidget(label("Theme"))
        line.addStretch()
        self.theme_select = QComboBox()
        self.theme_select.addItems(["Dark", "Light"])
        self.theme_select.setCurrentIndex(0 if self.settings["theme"] == "dark" else 1)
        self.theme_select.currentIndexChanged.connect(self._update_settings)
        line.addWidget(self.theme_select)
        appearance_box.addLayout(line)
        language_line = QHBoxLayout()
        language_line.addWidget(label("Language"))
        language_line.addStretch()
        self.language_select = QComboBox()
        self.language_select.addItems(["English", "Русский"])
        self.language_select.setCurrentIndex(0 if self.settings.get("language", "en") == "en" else 1)
        self.language_select.currentIndexChanged.connect(self._update_settings)
        language_line.addWidget(self.language_select)
        appearance_box.addLayout(language_line)
        appearance_box.addWidget(label("Crimson red is the brand accent; errors, warnings and success retain distinct status colors.",
                                       "Detail", wrap=True))
        layout.addWidget(appearance)
        privacy, privacy_box = card("PRIVACY & LOCAL DATA")
        self.save_history_toggle = QCheckBox("Save scan history on this computer")
        self.save_history_toggle.setChecked(self.settings["save_history"])
        self.save_history_toggle.toggled.connect(self._update_settings)
        privacy_box.addWidget(self.save_history_toggle)
        self.storage_label = label(f"Storage location: {self.storage_dir}", "Detail", wrap=True)
        self.storage_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        privacy_box.addWidget(self.storage_label)
        privacy_box.addWidget(label("History stores project paths and a snapshot of diagnostic findings."
                                     " No analytics or automatic uploads. GitHub imports require an explicit click.",
                                     "Detail", wrap=True))
        privacy_box.addWidget(button("Delete stored history", self._clear_history))
        layout.addWidget(privacy)
        about, about_box = card("ABOUT")
        about_box.addWidget(label(f"RepoMedic {__version__} · Developer Pro"))
        about_box.addWidget(label("Open-source static project diagnostics · MIT License", "Detail"))
        about_box.addWidget(label("Health Score is a heuristic, not a security certificate."
                                  " Scanner may miss issues and does not validate project execution.",
                                  "Detail", wrap=True))
        layout.addWidget(about)
        layout.addStretch()
        return viewport

    def _setup_table(self, table: QTableWidget):
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setMinimumSectionSize(65)
        table.setWordWrap(False)
        table.setShowGrid(False)

    def _register_shortcuts(self):
        """Predictable desktop shortcuts without changing existing workflows."""
        self.shortcut_open = QShortcut(QKeySequence("Ctrl+O"), self)
        self.shortcut_open.activated.connect(self.choose_folder)
        self.shortcut_scan = QShortcut(QKeySequence("Ctrl+R"), self)
        self.shortcut_scan.activated.connect(self.scan_local)
        self.shortcut_export = QShortcut(QKeySequence("Ctrl+E"), self)
        self.shortcut_export.activated.connect(self.export_report)
        self.header_choose.setToolTip("Ctrl+O")
        self.hero_run.setToolTip("Ctrl+R")
        self.scan_button.setToolTip("Ctrl+R")
        self.export_button.setToolTip("Ctrl+E")

    def _t(self, text: str) -> str:
        return translate(text, self.settings.get("language", "en"))

    def _translate_controls(self):
        """Translate only whitelisted UI labels; leave project content intact."""
        for widget in [ *self.findChildren(QLabel), *self.findChildren(QAbstractButton) ]:
            original = widget.property("i18n_source")
            if original is None:
                original = widget.text()
                # Dynamic findings and paths are never part of the whitelist.
                widget.setProperty("i18n_source", original)
            # Do not override fields populated with live values or project metadata.
            if translate(original, "ru") != original:
                widget.setText(self._t(original))
        # Navigation buttons include a glyph prefix, so translate their
        # fixed captions separately from the ordinary UI-text allowlist.
        # Always translate from the original English caption so switching
        # back to English works too.
        for nav in self.nav_buttons:
            original = nav.property("i18n_source") or nav.text()
            nav.setText(translate_navigation(original, self.settings.get("language", "en")))
        for combo in self.findChildren(QComboBox):
            originals = combo.property("i18n_items")
            if originals is None:
                originals = [combo.itemText(i) for i in range(combo.count())]
                combo.setProperty("i18n_items", originals)
            for i, original in enumerate(originals):
                if i < combo.count():
                    combo.setItemText(i, self._t(original))
        for table in self.findChildren(QTableWidget):
            originals = table.property("i18n_headers")
            if originals is None:
                originals = [table.horizontalHeaderItem(i).text() for i in range(table.columnCount())]
                table.setProperty("i18n_headers", originals)
            for i, original in enumerate(originals):
                if i < table.columnCount():
                    table.horizontalHeaderItem(i).setText(self._t(original))
        originals = self.findings.property("i18n_headers")
        if originals is None:
            originals = [self.findings.headerItem().text(i) for i in range(self.findings.columnCount())]
            self.findings.setProperty("i18n_headers", originals)
        for i, original in enumerate(originals):
            self.findings.headerItem().setText(i, self._t(original))
        self.sparkline.language = self.settings.get("language", "en")
        self.sparkline.update()
        self.raw_output.setPlaceholderText(self._t("Run a diagnosis to generate an exportable report."))
        if self.report is None:
            self.report_caption.setText(self._t("No report loaded"))
            self.scanner_count.setText(self._t("No scan yet"))
        self.storage_label.setText(("Папка данных: " if self.settings.get("language") == "ru" else
                                    "Storage location: ") + str(self.storage_dir))

    def _adjust_dashboard_layout(self):
        if not hasattr(self, "metrics_grid"):
            return
        # Use available center area, not display resolution. Works at 1000 px.
        narrow = self.width() - 244 < 1050
        if self._responsive_narrow == narrow:
            return
        self._responsive_narrow = narrow
        grid = self.metrics_grid
        for frame in [self.health_card, *self.stat_cards]:
            grid.removeWidget(frame)
        if narrow:
            grid.addWidget(self.health_card, 0, 0, 1, 2)
            for i, frame in enumerate(self.stat_cards):
                grid.addWidget(frame, 1 + i // 2, i % 2)
            for col in range(2):
                grid.setColumnStretch(col, 1)
            for col in range(2, 6):
                grid.setColumnStretch(col, 0)
        else:
            grid.addWidget(self.health_card, 0, 0, 1, 2)
            for i, frame in enumerate(self.stat_cards):
                grid.addWidget(frame, 0, i + 2)
            for col in range(6):
                grid.setColumnStretch(col, 2 if col < 2 else 1)
        direction = (QBoxLayout.Direction.TopToBottom if narrow else
                     QBoxLayout.Direction.LeftToRight)
        self.overview_layout.setDirection(direction)
        self.bottom_layout.setDirection(direction)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._adjust_dashboard_layout()

    def _navigate(self, index: int):
        if self._page_animation is not None:
            self._page_animation.stop()
        if self._animated_page is not None:
            self._animated_page.setGraphicsEffect(None)
            self._animated_page = None
        old = self.pages.currentIndex()
        self.pages.setCurrentIndex(index)
        if old != index:
            page = self.pages.currentWidget()
            effect = QGraphicsOpacityEffect(page)
            page.setGraphicsEffect(effect)
            fade = QPropertyAnimation(effect, b"opacity", self)
            fade.setDuration(170)
            fade.setStartValue(0.55)
            fade.setEndValue(1.0)
            fade.setEasingCurve(QEasingCurve.Type.OutCubic)
            fade.finished.connect(lambda current=page: current.setGraphicsEffect(None))
            self._animated_page = page
            self._page_animation = fade
            fade.start()
        for pos, nav in enumerate(self.nav_buttons):
            nav.setChecked(pos == index)
        if index == 2:
            self._refresh_history()

    def _apply_theme(self):
        theme = self.settings["theme"]
        self.setStyleSheet(stylesheet(theme))
        self.gauge.theme = theme
        self.gauge.update()
        self.sparkline.theme = theme
        self.sparkline.update()
        # QTableWidgetItem text colors are palette dependent.
        if self.report is not None:
            self._fill_findings()

    @Slot()
    def _update_settings(self, *_args):
        language_before = self.settings.get("language", "en")
        self.settings["theme"] = "dark" if self.theme_select.currentIndex() == 0 else "light"
        self.settings["language"] = "en" if self.language_select.currentIndex() == 0 else "ru"
        self.settings["save_history"] = self.save_history_toggle.isChecked()
        self._apply_theme()
        if language_before != self.settings["language"]:
            self._translate_controls()
            self._update_ui()
        try:
            save_settings(self.storage_dir, self.settings)
        except OSError as exc:
            QMessageBox.warning(self, "Settings", f"Could not save settings: {exc}")

    def _update_ui(self):
        self.scan_button.setEnabled(self.folder is not None and self._thread is None)
        self.hero_run.setEnabled(self.folder is not None and self._thread is None)
        self.export_button.setEnabled(self.report is not None and self._thread is None)
        chosen = str(self.folder) if self.folder is not None else self._t("Local project not selected")
        self.folder_label.setText(chosen)
        self.folder_label.setToolTip(chosen)
        if self.report:
            self.project_path.setText(self.report_label + "  ·  " +
                                      ("GitHub ZIP" if self.report.source == "github" else str(self.report.folder)))
            self.project_path.setToolTip(self.project_path.text())
        else:
            self.project_path.setText(chosen if self.folder else self._t("No project selected"))
        self.hero_project.setText(self.report_label if self.report else
                                  (self.folder.name if self.folder else self._t("No project selected")))
        self.hero_hint.setText((self._t("GitHub ZIP · imported for static scanning") if self.report.source == "github"
                                else str(self.report.folder)) if self.report else
                               (str(self.folder) if self.folder else self._t("Choose a folder or import a public GitHub repository.")))
        if self.report is None:
            self.report_caption.setText(self._t("No report loaded"))
        self._refresh_metrics()
        self._refresh_history()
        self._refresh_recommendations()
        self._refresh_overview()
        self._refresh_performance()

    def _refresh_metrics(self):
        if self.report is None:
            self.gauge.set_score(None)
            self.health_title.setText(self._t("Not scanned"))
            for metric in ("ERRORS", "WARNINGS", "PASSED CHECKS"):
                self.metric_values[metric].setText("—")
            self.health_bar.setValue(0)
        else:
            score = self.report.score()
            counts = self.report.counts()
            self.gauge.set_score(score)
            self.health_title.setText(self._t("Good" if score >= 85 else "Needs review" if score >= 60 else "Attention needed"))
            self.metric_values["ERRORS"].setText(str(counts["ERROR"]))
            self.metric_values["WARNINGS"].setText(str(counts["WARN"]))
            self.metric_values["PASSED CHECKS"].setText(str(counts["OK"]))
            self.health_bar.setValue(score)
        self.metric_values["LAST SCAN"].setText(
            fmt_date(self._last_scan_at).split("  ")[-1]
            if self.report and self._last_scan_at is not None else (self._t("Just now") if self.report else "—"))

    def _refresh_recommendations(self):
        clear_layout(self.recommendations_layout)
        if not self.report:
            self.recommendations_layout.addWidget(label(self._t("Run a scan to see actionable recommendations."), "Detail", wrap=True))
            return
        issues = [f for f in self.report.findings if f.level in ("ERROR", "WARN")]
        if not issues:
            self.recommendations_layout.addWidget(label(self._t("✓ No issues detected by the supported static checks."),
                                                         "Green", wrap=True))
        for i, issue in enumerate(issues[:6], 1):
            inner, inner_box = card(role="InnerPanel")
            inner_box.setContentsMargins(11, 9, 11, 9)
            inner_box.setSpacing(5)
            inner_box.addWidget(label(f"{i:02d}  {issue.section}", "Accent" if issue.level == "ERROR" else "CardTitle"))
            inner_box.addWidget(label(issue.message, wrap=True))
            if issue.advice:
                inner_box.addWidget(label(issue.advice, "Detail", wrap=True))
            self.recommendations_layout.addWidget(inner)
        if len(issues) > 6:
            self.recommendations_layout.addWidget(label(f"+ {len(issues)-6} more results in Scanner", "Detail"))

    def _refresh_overview(self):
        self.diagnostic_table.setRowCount(0)
        if not self.report:
            return
        sections: dict[str, list] = {}
        for item in self.report.findings:
            sections.setdefault(item.section, []).append(item)
        for section, findings in sections.items():
            row = self.diagnostic_table.rowCount()
            self.diagnostic_table.insertRow(row)
            status = ("ERROR" if any(f.level == "ERROR" for f in findings) else
                      "WARN" if any(f.level == "WARN" for f in findings) else "OK")
            issues = sum(f.level in ("WARN", "ERROR") for f in findings)
            cell = _cell(section)
            cell.setToolTip(section)
            self.diagnostic_table.setItem(row, 0, cell)
            status_item = _cell(status)
            colors = COLORS[self.settings["theme"]]
            status_item.setForeground(QBrush(QColor(colors[{"ERROR": "red", "WARN": "yellow", "OK": "green"}[status]])))
            self.diagnostic_table.setItem(row, 1, status_item)
            details = f"{len(findings)} checks · {issues} issues" if self.settings.get("language") != "ru" else f"Проверок: {len(findings)} · проблем: {issues}"
            self.diagnostic_table.setItem(row, 2, _cell(details))
        self.diagnostic_table.setMinimumHeight(min(390, 44 + self.diagnostic_table.rowCount()*34))

    def _show_scanner_for_section(self, row: int):
        section = self.diagnostic_table.item(row, 0)
        if section:
            self._navigate(1)
            for i in range(self.findings.topLevelItemCount()):
                item = self.findings.topLevelItem(i)
                if item.text(1) == section.text():
                    self.findings.setCurrentItem(item)
                    self.findings.scrollToItem(item)
                    break

    def _fill_findings(self):
        self.findings.clear()
        if not self.report:
            return
        colors = COLORS[self.settings["theme"]]
        mapping = {"OK": "green", "ERROR": "red", "WARN": "yellow", "INFO": "muted", "SKIP": "muted"}
        for finding in self.report.findings:
            item = QTreeWidgetItem([finding.level, finding.section, finding.message])
            item.setForeground(0, QBrush(QColor(colors[mapping.get(finding.level, "text")])))
            item.setData(0, Qt.ItemDataRole.UserRole, finding.advice or "")
            item.setToolTip(1, finding.section)
            item.setToolTip(2, finding.message)
            self.findings.addTopLevelItem(item)
        self._apply_filter()
        self.scanner_count.setText(f"{len(self.report.findings)} findings" if self.settings.get("language") != "ru" else f"Результатов: {len(self.report.findings)}")
        self.finding_detail.setText(self._t("Select a result to see its explanation and recommendations."))

    @Slot()
    def _apply_filter(self, *_args):
        mode = self.severity_filter.currentIndex()
        for index in range(self.findings.topLevelItemCount()):
            item = self.findings.topLevelItem(index)
            level = item.text(0)
            visible = (mode == 0 or (mode == 1 and level in ("WARN", "ERROR")) or
                       (mode == 2 and level == "ERROR") or (mode == 3 and level == "WARN") or
                       (mode == 4 and level == "OK"))
            item.setHidden(not visible)

    def _show_finding_details(self, item: QTreeWidgetItem | None, _previous):
        if item is None:
            return
        advice = item.data(0, Qt.ItemDataRole.UserRole)
        self.finding_detail.setText(
            f"{item.text(1)} — {item.text(2)}" + (f"\n\n{'Рекомендация' if self.settings.get('language') == 'ru' else 'Recommendation'}: {advice}" if advice else ""))

    def _refresh_performance(self):
        self.duration_text.setText(time_label(self.scan_seconds) if self.report else "—")
        self.sparkline.set_values([float(x.get("duration_seconds", 0)) for x in reversed(self.history)
                                   if isinstance(x.get("duration_seconds"), (int, float))])

    def _refresh_history(self):
        self.recent_table.setRowCount(0)
        self.history_table.setRowCount(0)
        for index, item in enumerate(self.history):
            row = self.history_table.rowCount()
            self.history_table.insertRow(row)
            counts = item.get("counts", {})
            columns = [fmt_date(item.get("date_utc", "")), str(item.get("label", "—")),
                       "GitHub" if item.get("source") == "github" else "Local",
                       str(item.get("score", "—")) + "/100",
                       str(counts.get("ERROR", 0)) + " errors · " + str(counts.get("WARN", 0)) + " warnings",
                       time_label(float(item.get("duration_seconds", 0)))]
            for col, value in enumerate(columns):
                self.history_table.setItem(row, col, _cell(value))
            if index < 4:
                recent = self.recent_table.rowCount()
                self.recent_table.insertRow(recent)
                for col, value in enumerate([columns[0], columns[1], columns[3]]):
                    self.recent_table.setItem(recent, col, _cell(value))
        self.history_note.setText((f"Локальных записей: {len(self.history)}" if self.settings.get("language") == "ru" else f"{len(self.history)} scans saved locally") if self.history else
                                  ("История пуста. Запустите диагностику." if self.settings.get("language") == "ru" else "No saved scans. Run diagnostics to begin building history."))

    def _load_history_row(self, row: int, _col: int):
        if not (0 <= row < len(self.history)):
            return
        entry = self.history[row]
        self.report = restore_report(entry)
        self.report_label = str(entry.get("label", self.report.folder.name))
        self.scan_seconds = float(entry.get("duration_seconds", 0))
        self._last_scan_at = entry.get("date_utc")
        # Do not accidentally scan a deleted temp ZIP folder loaded from history.
        self.folder = None
        self._fill_findings()
        self.raw_output.setPlainText(self.report.to_text())
        self.report_caption.setText("Saved scan · " + self.report_label)
        self._update_ui()
        self._navigate(0)
        self.statusBar().showMessage("Historical report loaded — project files were not rescanned")

    def _clear_history(self):
        if not self.history:
            return
        answer = QMessageBox.question(self, "Delete local history", "Delete every saved scan record? This cannot be undone.")
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            clear_history(self.storage_dir)
        except OSError as exc:
            QMessageBox.warning(self, "History", str(exc))
            return
        self.history.clear()
        self._update_ui()
        self.statusBar().showMessage("Local scan history cleared")

    def choose_folder(self):
        selected = QFileDialog.getExistingDirectory(self, "Choose project folder")
        if selected:
            self.folder = Path(selected)
            self.report = None
            self.report_label = ""
            self._last_scan_at = None
            self.findings.clear()
            self.raw_output.clear()
            self.report_caption.setText(self._t("No report loaded"))
            self.scanner_count.setText(self._t("No scan yet"))
            self._update_ui()
            self._navigate(1)
            self.statusBar().showMessage(("Папка выбрана · готово к проверке" if self.settings.get("language") == "ru" else "Folder selected · ready to scan"))

    def scan_local(self):
        if self.folder is not None:
            self._start_scan(folder=self.folder)
        else:
            self._navigate(1)

    def scan_github(self):
        url = self.github_input.text().strip()
        try:
            parse_github_url(url)
        except (ValueError, DownloadError) as exc:
            QMessageBox.warning(self, "Invalid GitHub URL", str(exc))
            return
        self._start_scan(github_url=url)

    def _start_scan(self, folder: Path | None = None, github_url: str = ""):
        if self._thread is not None:
            return
        self._cleanup_imports()
        self.report = None
        self.report_label = ""
        self._last_scan_at = None
        self.findings.clear()
        self.raw_output.clear()
        self.scanner_count.setText(self._t("Scanning…"))
        self._update_ui()
        self.header_choose.setEnabled(False)
        self.github_button.setEnabled(False)
        self.github_input.setEnabled(False)
        self.scan_button.setEnabled(False)
        self.hero_run.setEnabled(False)
        self.busy.show()
        self.header_busy.show()
        self.header_status.setText(self._t("● Scanning"))
        self.statusBar().showMessage(("Загрузка и анализ…" if github_url else "Проверка локальных файлов…") if self.settings.get("language") == "ru" else ("Importing and analyzing…" if github_url else "Analyzing local files…"))
        thread = QThread(self)
        worker = ScanWorker(folder, github_url)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.completed.connect(self._render_result)
        worker.failed.connect(self._show_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._finish_scan)
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        self._worker = worker
        thread.start()

    @Slot(object)
    def _render_result(self, result: object):
        report, temporary, seconds, display_name = result
        self.report = report
        self.report_label = display_name
        self.scan_seconds = seconds
        self._last_scan_at = datetime.now(timezone.utc).isoformat()
        if temporary is not None:
            self._temporary_folders.append(temporary)
            self.folder = None
        self.raw_output.setPlainText(report.to_text())
        self.report_caption.setText(f"{display_name} · {report.score()}/100 · {time_label(seconds)}")
        self._fill_findings()
        if self.settings["save_history"]:
            try:
                self.history = add_to_history(self.history, snapshot(report, seconds, display_name))
                save_history(self.storage_dir, self.history)
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, "History", f"Scan succeeded, but history was not saved: {exc}")
        self._update_ui()
        self._navigate(0)
        self.statusBar().showMessage((f"Проверка завершена · {time_label(seconds)} · результатов: {len(report.findings)}") if self.settings.get("language") == "ru" else f"Scan completed · {time_label(seconds)} · {len(report.findings)} checks")

    @Slot(str)
    def _show_error(self, message: str):
        self.scanner_count.setText(self._t("Scan failed"))
        self.statusBar().showMessage(self._t("Scan failed"))
        QMessageBox.warning(self, "RepoMedic", message)

    @Slot()
    def _finish_scan(self):
        self._thread = None
        self._worker = None
        self.header_choose.setEnabled(True)
        self.github_button.setEnabled(True)
        self.github_input.setEnabled(True)
        self.busy.hide()
        self.header_busy.hide()
        self.header_status.setText(self._t("● Ready"))
        self._update_ui()

    def export_report(self):
        if self.report is None:
            return
        selected = self.export_format.currentText().lower()
        suffix = "." + ("txt" if selected == "txt" else selected)
        path, _ = QFileDialog.getSaveFileName(
            self, "Export diagnosis", str(Path.home() / ("repomedic-report" + suffix)),
            {"txt": "Text (*.txt)", "json": "JSON (*.json)", "html": "HTML (*.html)"}[selected])
        if not path:
            return
        target = Path(path)
        if target.suffix.lower() != suffix:
            target = target.with_suffix(suffix)
        try:
            content = {"txt": self.report.to_text, "json": self.report.to_json,
                       "html": lambda: render_html_report(self.report)}[selected]()
            atomic_save_text(target, content)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Export failed", str(exc))
            return
        self.statusBar().showMessage((f"Отчёт сохранён: {target}") if self.settings.get("language") == "ru" else f"Report saved: {target}")

    def _cleanup_imports(self):
        for temp in self._temporary_folders:
            shutil.rmtree(temp, ignore_errors=True)
        self._temporary_folders.clear()

    def closeEvent(self, event):
        if self._thread is not None:
            QMessageBox.information(self, "Scan running", "Please wait until the current scan finishes.")
            event.ignore()
            return
        self._cleanup_imports()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("RepoMedic")
    app.setOrganizationName("RepoMedic")
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

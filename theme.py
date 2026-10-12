"""RepoMedic v1.0 Developer Pro stylesheet tokens."""
from __future__ import annotations

COLORS = {
    "dark": {
        "bg": "#0C1019", "sidebar": "#111722", "surface": "#151D29", "card": "#192230",
        "card_alt": "#1D2837", "border": "#2A3545", "text": "#F3F5F9", "muted": "#9BAABD",
        "accent": "#E63848", "accent_hover": "#FC4C5B", "field": "#101723", "selected": "#3B232F",
        "track": "#313946", "green": "#4BD399", "yellow": "#F6BC56", "red": "#FF6577",
    },
    "light": {
        "bg": "#F4F6FA", "sidebar": "#EBEEF4", "surface": "#FFFFFF", "card": "#FFFFFF",
        "card_alt": "#F3F5F9", "border": "#D9DFE9", "text": "#172132", "muted": "#5C6B7F",
        "accent": "#CF283B", "accent_hover": "#E83C51", "field": "#F9FAFC", "selected": "#F7DDE1",
        "track": "#D7DCE6", "green": "#16875B", "yellow": "#9A640D", "red": "#CF263E",
    },
}


def stylesheet(theme: str) -> str:
    c = COLORS.get(theme, COLORS["dark"])
    return """
    QWidget {font-family:'Segoe UI', 'Arial';font-size:14px;color:%(text)s;}
    QWidget#AppRoot { background:%(bg)s; }
    QFrame#Sidebar {background:%(sidebar)s;border-right:1px solid %(border)s;}
    QFrame#Topbar {background:%(surface)s;border-bottom:1px solid %(border)s;}
    QFrame#Card, QFrame#Hero, QFrame#InnerPanel {background:%(card)s;border:1px solid %(border)s;border-radius:14px;}
    QFrame#Hero {background:%(surface)s;}
    QFrame#InnerPanel {background:%(card_alt)s;}
    QLabel {background:transparent;}
    QLabel#BrandName {font-size:19px;font-weight:800;}
    QLabel#SectionTitle {font-size:24px;font-weight:800;}
    QLabel#HeroTitle {font-size:28px;font-weight:800;}
    QLabel#CardTitle {font-size:15px;font-weight:700;}
    QLabel#MetricNumber {font-size:30px;font-weight:800;}
    QLabel#MetricCaption {font-size:12px;font-weight:700;color:%(muted)s;}
    QLabel#Muted, QLabel#Detail, QLabel#Hint {color:%(muted)s;}
    QLabel#Detail {font-size:13px;}
    QLabel#Accent {color:%(accent)s;font-weight:700;}
    QLabel#Green {color:%(green)s;font-weight:700;}
    QLabel#Yellow {color:%(yellow)s;font-weight:700;}
    QLabel#Red {color:%(red)s;font-weight:700;}
    QPushButton {background:%(card_alt)s;border:1px solid %(border)s;color:%(text)s;
        border-radius:9px;padding:10px 16px;font-weight:600;min-height:18px;}
    QPushButton:hover:enabled {background:%(selected)s;border-color:%(accent)s;}
    QPushButton:disabled {color:%(muted)s;background:%(surface)s;}
    QPushButton#Primary {background:%(accent)s;border:1px solid %(accent)s;color:white;font-weight:800;}
    QPushButton#Primary:hover:enabled {background:%(accent_hover)s;}
    QPushButton#Nav {background:transparent;border:0;border-radius:9px;text-align:left;
        padding:11px 14px;font-size:14px;font-weight:600;}
    QPushButton#Nav:hover {background:%(card_alt)s;border:0;}
    QPushButton#Nav:checked {background:%(selected)s;border-left:3px solid %(accent)s;border-radius:8px;}
    QPushButton#Ghost {background:transparent;border:1px solid %(border)s;}
    QLineEdit, QComboBox, QPlainTextEdit, QTreeWidget, QTableWidget {
        background:%(field)s;border:1px solid %(border)s;color:%(text)s;border-radius:9px;
        padding:9px;selection-background-color:%(accent)s;}
    QLineEdit:focus, QComboBox:focus {border:1px solid %(accent)s;}
    QComboBox QAbstractItemView {background:%(surface)s;color:%(text)s;selection-background-color:%(selected)s;}
    QPlainTextEdit {font-family:'Consolas','Cascadia Code',monospace;font-size:12px;}
    QTreeWidget, QTableWidget {alternate-background-color:%(card_alt)s;gridline-color:%(border)s;}
    QTreeWidget::item, QTableWidget::item {padding:6px;}
    QHeaderView::section {background:%(card_alt)s;color:%(muted)s;border:0;
        border-bottom:1px solid %(border)s;padding:9px;font-size:12px;font-weight:700;}
    QProgressBar {background:%(track)s;border:0;border-radius:4px;min-height:7px;max-height:7px;}
    QProgressBar::chunk {background:%(accent)s;border-radius:4px;}
    QScrollArea {border:0;background:transparent;}
    QScrollArea > QWidget > QWidget {background:transparent;}
    QCheckBox {spacing:10px;}
    QCheckBox::indicator {width:18px;height:18px;}
    QStatusBar {background:%(surface)s;color:%(muted)s;border-top:1px solid %(border)s;}
    QSplitter::handle {background:%(border)s;}
    """ % c

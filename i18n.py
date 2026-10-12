"""Localized GUI chrome for RepoMedic; source-language diagnostics remain unchanged.

UI translation is deliberately an allowlist so repository-provided text is never
translated or misinterpreted as application UI.
"""
from __future__ import annotations

LANGUAGES = ("en", "ru")

RU = {
    "Dashboard": "Главная", "Scanner": "Сканер", "History": "История",
    "Reports": "Отчёты", "Settings": "Настройки", "Open folder": "Открыть папку",
    "● Ready": "● Готово", "● Scanning": "● Проверка",
    "PROJECT OVERVIEW": "О ПРОЕКТЕ", "No project selected": "Проект не выбран",
    "Select a local folder or import from GitHub in Scanner.": "Выберите папку или импортируйте проект с GitHub в сканере.",
    "▶  Run Diagnostics": "▶  Начать проверку", "PROJECT HEALTH SCORE": "СОСТОЯНИЕ ПРОЕКТА",
    "Not scanned": "Нет проверки", "Good": "Хорошо", "Needs review": "Нужна проверка",
    "Attention needed": "Нужны исправления",
    "ERRORS": "ОШИБКИ", "WARNINGS": "ПРЕДУПРЕЖДЕНИЯ",
    "PASSED CHECKS": "ПРОЙДЕНО", "LAST SCAN": "ПОСЛЕДНЯЯ ПРОВЕРКА",
    "DIAGNOSTICS OVERVIEW": "ОБЗОР ДИАГНОСТИКИ", "TOP RECOMMENDATIONS": "РЕКОМЕНДАЦИИ",
    "Category": "Категория", "Status": "Статус", "Checks": "Проверки",
    "View all diagnostics  →": "Все результаты  →", "RECENT SCANS": "ПОСЛЕДНИЕ ПРОВЕРКИ",
    "Date": "Дата", "Project": "Проект", "Score": "Оценка",
    "Open scan history  →": "Вся история  →", "SCAN PERFORMANCE": "СКОРОСТЬ ПРОВЕРКИ",
    "Measured local scan duration; GitHub scans include download time.": "Фактическое время анализа; импорт с GitHub включает загрузку.",
    "Project Scanner": "Сканер проектов",
    "Analyze Python, Node.js, Docker and GitHub configuration — read-only static checks.": "Статический анализ Python, Node.js, Docker и GitHub без запуска кода.",
    "PROJECT SOURCE": "ИСТОЧНИК ПРОЕКТА", "Local project not selected": "Локальная папка не выбрана",
    "Choose folder": "Выбрать папку", "Import GitHub": "Импорт GitHub",
    "▶  Scan selected folder": "▶  Проверить папку", "CHECK RESULTS": "РЕЗУЛЬТАТЫ",
    "Severity": "Уровень", "All results": "Все результаты", "Issues only": "Только проблемы",
    "Errors": "Ошибки", "Warnings": "Предупреждения", "Passed": "Пройденные",
    "No scan yet": "Проверок пока нет", "Section": "Раздел", "Diagnostic result": "Результат проверки",
    "Select a result to see its explanation and recommendations.": "Выберите результат, чтобы увидеть пояснение и рекомендацию.",
    "🔒  Repository code is never executed. GitHub import downloads a bounded ZIP archive.": "🔒  Код проекта не запускается. С GitHub загружается ограниченный ZIP-архив.",
    "Scan History": "История проверок", "Clear history": "Очистить историю",
    "Saved locally on this computer. Double-click a row to inspect an earlier report.": "Данные хранятся локально. Дважды нажмите строку, чтобы открыть предыдущий отчёт.",
    "PREVIOUS DIAGNOSTICS": "ПРЕДЫДУЩИЕ ПРОВЕРКИ", "Source": "Источник",
    "Health": "Оценка", "Issues": "Проблемы", "Time": "Время",
    "No saved scans yet.": "История пока пуста.",
    "Inspect the last selected scan and export a complete TXT, JSON or HTML report.": "Просмотрите результаты и сохраните отчёт в TXT, JSON или HTML.",
    "REPORT PREVIEW": "ПРЕДПРОСМОТР ОТЧЁТА", "No report loaded": "Отчёт не загружен",
    "Export report": "Сохранить отчёт", "Run a diagnosis to generate an exportable report.": "Запустите проверку, чтобы получить отчёт.",
    "HTML export is a self-contained local file. Existing export formats remain supported.": "HTML-отчёт открывается локально в браузере. Доступны также TXT и JSON.",
    "Customize RepoMedic without affecting project files.": "Настройки не изменяют файлы проектов.",
    "APPEARANCE": "ВНЕШНИЙ ВИД", "Theme": "Тема", "Language": "Язык",
    "Dark": "Тёмная", "Light": "Светлая",
    "Crimson red is the brand accent; errors, warnings and success retain distinct status colors.": "Фирменный цвет — красный; статусы ошибок, предупреждений и успешных проверок различаются цветом.",
    "PRIVACY & LOCAL DATA": "ПРИВАТНОСТЬ И ДАННЫЕ",
    "Save scan history on this computer": "Сохранять историю проверок на компьютере",
    "History stores project paths and a snapshot of diagnostic findings. No analytics or automatic uploads. GitHub imports require an explicit click.": "История хранит пути проектов и результаты проверок. Телеметрии и автоматических загрузок нет. Импорт GitHub — только по вашему действию.",
    "Delete stored history": "Удалить историю", "ABOUT": "О ПРОГРАММЕ",
    "Open-source static project diagnostics · MIT License": "Статическая диагностика проектов с открытым кодом · MIT",
    "Health Score is a heuristic, not a security certificate. Scanner may miss issues and does not validate project execution.": "Оценка проекта приблизительна, не является сертификатом безопасности и не гарантирует запуск проекта.",
    "Local project diagnostics without executing untrusted project code.": "Локальная проверка проектов без выполнения чужого кода.",
    "Open Source · MIT License": "Открытый код · MIT",
    "A heuristic based on detected warnings and errors — not a security audit.": "Приблизительная оценка по ошибкам и предупреждениям — не аудит безопасности.",
    "Run a scan to see actionable recommendations.": "Запустите проверку, чтобы увидеть рекомендации.",
    "✓ No issues detected by the supported static checks.": "✓ Поддерживаемые проверки проблем не выявили.",
    "RepoMedic 1.0.0 · Developer Pro": "RepoMedic 1.0.0 · Developer Pro",
    "Just now": "Только что", "GitHub ZIP · imported for static scanning": "GitHub ZIP · статическая проверка",
    "Choose a folder or import a public GitHub repository.": "Выберите папку или импортируйте публичный репозиторий GitHub.",
    "Trend available after 2 scans": "График появится после двух проверок",
    "Ready · select a project to begin": "Готово · выберите проект",
    "Scanning…": "Проверка…", "Scan failed": "Ошибка сканирования",
}


def translate(text: str, language: str) -> str:
    if language not in LANGUAGES:
        language = "en"
    if language == "en":
        return text
    return RU.get(text, text)


NAVIGATION_KEYS = frozenset(("Dashboard", "Scanner", "History", "Reports", "Settings"))


def translate_navigation(text: str, language: str) -> str:
    """Translate only fixed navigation labels while retaining their icon prefix.

    Nav button captions carry a symbol plus three spaces, such as
    "⌂   Dashboard". The ordinary translation allowlist matches only
    "Dashboard", so translating the entire button text would skip it.
    """
    prefix, separator, caption = text.partition("   ")
    if separator and caption in NAVIGATION_KEYS:
        return f"{prefix}{separator}{translate(caption, language)}"
    return text

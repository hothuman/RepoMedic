# RepoMedic v1.0.0 — Developer Pro

**Бесплатный Open Source-инструмент для статической диагностики проектов.** Проверяет доступные конфигурации Python, Node.js, Docker, Git и GitHub Actions без запуска кода анализируемого проекта. Поддерживаются Windows/Linux, GUI, CLI, переключение RU/EN, светлая/тёмная темы, локальная история и экспорт TXT/JSON/HTML.

> **Важно:** Health Score — приблизительная оценка на основе предупреждений. Программа не является антивирусом, аудитом безопасности или гарантией корректного запуска проекта.

## Обновление с v0.9.1 на Windows 11

1. Закрой RepoMedic и сделай резервную копию папки `папка вашего проекта RepoMedic`.
2. Распакуй исходный архив v1.0. Скопируй **содержимое `RepoMedic_v1.0`** в папку проекта с заменой файлов.
3. Не удаляй `.venv`. Сохранённые настройки и история находятся в `%LOCALAPPDATA%\RepoMedic`.
4. В PowerShell введи:

```powershell
cd C:\path\to\RepoMedic
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts\smoke_gui.py
.\.venv\Scripts\python.exe main.py
```

## Как подготовить Windows `.exe`

Для воспроизводимой сборки на Windows рекомендуем Python **3.13 x64** и PyInstaller из `requirements-build.txt`. Делай релизную сборку **в отдельной копии проекта** с новым `.venv`, чтобы не затронуть свою основную среду Python 3.15. Если в копии уже есть `.venv`, удали его только из копии.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\scripts\build_windows.ps1
.\scripts\smoke_exe.ps1
.\scripts\package_windows.ps1
```

Итог: папка `dist\RepoMedic` и ZIP `release\RepoMedic-Windows-x64-v1.0.0.zip`, рядом `SHA256SUMS.txt`. В ZIP должны находиться `.exe` и все зависимости. Пользователям не требуется Python.

**Нельзя считать `.exe` проверенным**, пока он не запустился хотя бы на одной другой Windows 11 без Python и не пройдены ручные проверки. Перед публикацией см. [чек-лист](docs/RELEASE_CHECKLIST.md).

## GitHub

В репозитории есть workflow для тестов на Windows/Linux, сборки Windows и публикации по Git-тегу `v1.0.0`. Публикация сработает только если проверки пройдут. Не создавай тег, пока не проверим итоговый `.exe`.

## Безопасность и приватность

Локальные проекты сканируются без изменения файлов. Импорт GitHub выполняется только по кнопке и скачивает архив. История хранит пути к проектам и текст результатов; её можно отключить и очистить. Телеметрия не предусмотрена. При сомнениях проверяй предупреждения вручную.

**Проект под MIT License.** Документация и исходный код включены. Интерфейс RU/EN; тексты диагностического движка не всегда переводятся.

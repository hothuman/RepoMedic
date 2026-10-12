"""Explicit, bounded download of public GitHub repo archives (no git execution)."""
from __future__ import annotations

import io
import re
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from version import __version__

ARCHIVE_LIMIT = 25 * 1024 * 1024
EXPANDED_LIMIT = 100 * 1024 * 1024
FILE_LIMIT = 4000
SEGMENT = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
# Windows forbids these device basenames even with a file extension.
_WINDOWS_DEVICE = re.compile(r"^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", re.I)


def _archive_parts(filename: str) -> tuple[str, ...]:
    """Validate ZIP member names for Linux and Windows before writing anything."""
    if (not filename or filename.startswith("/") or "\\" in filename
            or "\x00" in filename or len(filename) > 1024):
        raise DownloadError("Обнаружен небезопасный путь в архиве")
    components = filename.rstrip("/").split("/")
    if not components or len(components) > 30:
        raise DownloadError("Недопустимая вложенность ZIP-архива")
    for component in components:
        if (component in ("", ".", "..") or ":" in component or "<" in component
                or ">" in component or '"' in component or "|" in component
                or "?" in component or "*" in component
                or component.endswith((" ", ".")) or _WINDOWS_DEVICE.match(component)):
            raise DownloadError("Недопустимое для Windows имя в архиве")
    return tuple(components)



class DownloadError(Exception):
    """Friendly validation or network error from GitHub archive import."""


def parse_github_url(text: str) -> tuple[str, str]:
    text = text.strip()
    parts = urlsplit(text)
    if (parts.scheme != "https" or (parts.hostname or "").lower() != "github.com"
            or parts.username or parts.password or parts.port is not None
            or parts.query or parts.fragment):
        raise DownloadError("Укажите публичный адрес вида https://github.com/owner/repo")
    pieces = parts.path.strip("/").split("/")
    if len(pieces) != 2:
        raise DownloadError("Нужна ссылка на корень репозитория, без /tree/ или /blob/")
    owner, repo = pieces
    repo = repo.removesuffix(".git")
    if not SEGMENT.fullmatch(owner) or not SEGMENT.fullmatch(repo) or owner in (".", "..") or repo in (".", ".."):
        raise DownloadError("Некорректное имя владельца или репозитория")
    return owner, repo


class RestrictedRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlsplit(newurl)
        if parsed.scheme != "https" or parsed.hostname not in ("api.github.com", "codeload.github.com"):
            raise DownloadError("Загрузка перенаправлена на неподдерживаемый сервер")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def safe_extract(archive: zipfile.ZipFile, target: Path) -> Path:
    """Extract bounded ordinary files; reject path aliases on Windows and Linux."""
    members = archive.infolist()
    if not members or len(members) > FILE_LIMIT:
        raise DownloadError("Архив пуст или содержит слишком много файлов (предел 4000)")
    total_size = 0
    archive_root: str | None = None
    accepted: list[tuple[zipfile.ZipInfo, tuple[str, ...]]] = []
    seen: dict[tuple[str, ...], bool] = {}
    has_children: set[tuple[str, ...]] = set()

    # First pass: validate the whole central directory before writing any files.
    for member in members:
        parts = _archive_parts(member.filename)
        if archive_root is None:
            archive_root = parts[0]
        if parts[0] != archive_root or len(parts) < 2:
            # A directory entry containing only the root is harmless.
            if not (len(parts) == 1 and parts[0] == archive_root and member.is_dir()):
                raise DownloadError("Неожиданная структура ZIP-архива")
        mode = member.external_attr >> 16
        if stat.S_ISLNK(mode) or (mode and stat.S_IFMT(mode) not in (0, stat.S_IFDIR, stat.S_IFREG)):
            raise DownloadError("В ZIP разрешены только обычные файлы и каталоги")
        key = tuple(x.casefold() for x in parts)
        if key in seen:
            raise DownloadError("В ZIP обнаружены дублирующиеся пути (Windows case-insensitive)")
        for length in range(1, len(key)):
            if seen.get(key[:length]) is False:
                raise DownloadError("Файл ZIP конфликтует с именем каталога")
        if not member.is_dir() and key in has_children:
            raise DownloadError("Файл ZIP конфликтует с именем каталога")
        seen[key] = member.is_dir()
        for length in range(1, len(key)):
            has_children.add(key[:length])
        total_size += member.file_size
        if total_size > EXPANDED_LIMIT:
            raise DownloadError("Распакованный проект слишком большой (предел 100 МиБ)")
        if member.file_size > 25 * 1024 * 1024:
            raise DownloadError("Отдельный файл превышает предел 25 МиБ")
        accepted.append((member, parts))

    assert archive_root is not None
    base = target.resolve()
    for member, parts in accepted:
        destination = target.joinpath(*parts)
        if not destination.resolve().is_relative_to(base):
            raise DownloadError("Попытка записи за пределы временного каталога")
        if member.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member) as src, destination.open("wb") as dst:
            remaining = member.file_size
            while remaining:
                chunk = src.read(min(65536, remaining))
                if not chunk:
                    raise DownloadError("Повреждённый архив")
                dst.write(chunk)
                remaining -= len(chunk)
    return target / archive_root


def download_public_repo(url: str) -> tuple[Path, Path]:
    """Return (project_root, temporary_parent) for cleanup by caller."""
    owner, repo = parse_github_url(url)
    api_url = f"https://api.github.com/repos/{owner}/{repo}/zipball"
    req = Request(api_url, headers={
        "User-Agent": f"RepoMedic/{__version__} (read-only diagnostic tool)",
        "Accept": "application/vnd.github+json",
    })
    opener = build_opener(RestrictedRedirects())
    try:
        with opener.open(req, timeout=25) as response:
            buffer = io.BytesIO()
            while True:
                chunk = response.read(65536)
                if not chunk:
                    break
                if buffer.tell() + len(chunk) > ARCHIVE_LIMIT:
                    raise DownloadError("Слишком большой ZIP (предел 25 МиБ); скачайте вручную")
                buffer.write(chunk)
    except DownloadError:
        raise
    except Exception as exc:
        raise DownloadError(f"Не удалось скачать репозиторий: {exc}") from exc

    tmp = Path(tempfile.mkdtemp(prefix="repomedic-"))
    try:
        with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as archive:
            folder = safe_extract(archive, tmp)
        return folder, tmp
    except (OSError, ValueError, RuntimeError, EOFError, NotImplementedError, zipfile.BadZipFile, DownloadError) as exc:
        shutil.rmtree(tmp, ignore_errors=True)
        if isinstance(exc, DownloadError):
            raise
        raise DownloadError(f"Архив не удалось распаковать: {exc}") from exc

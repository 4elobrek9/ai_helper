import hashlib
import os
import re
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from urllib.parse import urlparse

import requests

from app_paths import data_path


GITHUB_PAGE = "https://github.com/4elobrek9/ScreenSage/releases/tag/AI"
RELEASE_API = "https://api.github.com/repos/4elobrek9/ScreenSage/releases/tags/AI"
ASSET_NAME = "ScreenSage_WIN.exe"
MAX_ASSET_SIZE = 250 * 1024 * 1024
_running_process = None
_ALLOWED_DOWNLOAD_HOSTS = {
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
}


def mods_directory():
    app_root = (
        Path(sys.executable).resolve().parent
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parent
    )
    return app_root / "MODS"


def executable_path():
    return mods_directory() / ASSET_NAME


def _ensure_settings():
    with closing(sqlite3.connect(data_path("config.db"))) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS screensage_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                autostart INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        connection.execute(
            "INSERT OR IGNORE INTO screensage_settings (id, autostart) VALUES (1, 0)"
        )
        connection.commit()


def is_autostart_enabled():
    _ensure_settings()
    with closing(sqlite3.connect(data_path("config.db"))) as connection:
        row = connection.execute(
            "SELECT autostart FROM screensage_settings WHERE id = 1"
        ).fetchone()
    return bool(row[0]) if row else False


def set_autostart_enabled(enabled):
    _ensure_settings()
    with closing(sqlite3.connect(data_path("config.db"))) as connection:
        connection.execute(
            "UPDATE screensage_settings SET autostart = ? WHERE id = 1",
            (int(bool(enabled)),),
        )
        connection.commit()


def is_installed():
    path = executable_path()
    if not path.is_file():
        return False
    try:
        with path.open("rb") as executable:
            return executable.read(2) == b"MZ"
    except OSError:
        return False


def download_latest(progress_callback=None):
    response = requests.get(
        RELEASE_API,
        headers={"Accept": "application/vnd.github+json"},
        timeout=(5, 15),
    )
    response.raise_for_status()
    release = response.json()
    if not isinstance(release, dict) or release.get("tag_name") != "AI":
        raise RuntimeError("GitHub не вернул ожидаемый релиз ScreenSage.")
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise RuntimeError("GitHub вернул некорректный список файлов ScreenSage.")
    asset = next(
        (
            item for item in assets
            if isinstance(item, dict) and item.get("name") == ASSET_NAME
        ),
        None,
    )
    if asset is None:
        raise RuntimeError("В релизе ScreenSage не найден Windows EXE.")
    asset_size = asset.get("size")
    if (
        not isinstance(asset_size, int)
        or asset_size <= 0
        or asset_size > MAX_ASSET_SIZE
    ):
        raise RuntimeError("Размер файла ScreenSage превышает допустимый предел.")

    digest = asset.get("digest")
    if not isinstance(digest, str) or not re.fullmatch(
        r"sha256:[0-9a-fA-F]{64}", digest
    ):
        raise RuntimeError(
            "GitHub не предоставил SHA-256 для этого файла; загрузка отменена."
        )
    download_url = asset.get("browser_download_url", "")
    expected_prefix = "https://github.com/4elobrek9/ScreenSage/releases/download/"
    if (
        not isinstance(download_url, str)
        or not download_url.startswith(expected_prefix)
    ):
        raise RuntimeError("Ссылка на EXE ведёт не на официальный GitHub-релиз.")

    destination = executable_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = destination.with_suffix(".exe.part")
    hasher = hashlib.sha256()
    downloaded = 0
    if progress_callback:
        progress_callback(0, asset_size)
    try:
        with requests.get(
            download_url,
            stream=True,
            allow_redirects=True,
            timeout=(5, 30),
        ) as download:
            download.raise_for_status()
            final_url = urlparse(download.url)
            if (
                final_url.scheme != "https"
                or final_url.hostname not in _ALLOWED_DOWNLOAD_HOSTS
            ):
                raise RuntimeError(
                    "GitHub перенаправил загрузку на недоверенный адрес."
                )
            with temporary_path.open("wb") as target:
                for chunk in download.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    downloaded += len(chunk)
                    if downloaded > asset_size or downloaded > MAX_ASSET_SIZE:
                        raise RuntimeError("Размер загрузки не совпадает с релизом.")
                    hasher.update(chunk)
                    target.write(chunk)
                    if progress_callback:
                        progress_callback(downloaded, asset_size)
        if downloaded != asset_size:
            raise RuntimeError("Загружен неполный файл ScreenSage.")
        if f"sha256:{hasher.hexdigest()}" != digest.lower():
            raise RuntimeError("SHA-256 ScreenSage не совпал с метаданными GitHub.")
        with temporary_path.open("rb") as downloaded_file:
            header = downloaded_file.read(2)
        if header != b"MZ":
            raise RuntimeError("Загруженный файл не похож на Windows EXE.")
        os.replace(temporary_path, destination)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    return destination


def launch():
    global _running_process
    path = executable_path()
    if not is_installed():
        raise RuntimeError("ScreenSage не установлен или файл повреждён.")
    if _running_process is not None and _running_process.poll() is None:
        return _running_process
    _running_process = subprocess.Popen([str(path)], cwd=str(path.parent))
    return _running_process


def remove():
    global _running_process
    path = executable_path()
    if _running_process is not None and _running_process.poll() is None:
        _running_process.terminate()
        try:
            _running_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _running_process.kill()
            _running_process.wait(timeout=5)
    _running_process = None
    if path.exists():
        path.unlink()
    set_autostart_enabled(False)

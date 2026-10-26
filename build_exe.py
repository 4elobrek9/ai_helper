"""Сборка LUMI AI в отдельный EXE-файл через PyInstaller."""

import subprocess
import sys
from pathlib import Path

PROJECT_NAME = "LUMI AI"
ENTRY_MODULE = "lumi.__main__"
ICON_FILE = "assets/icon.png"

ADD_DATA = [
    ("audio", "audio"),
    ("models", "models"),
    ("lumi_config.yaml", "."),
    ("command.json", "."),
    ("icon.png", "."),
    ("app_icon.png", "."),
]


def run(cmd: list[str]) -> None:
    subprocess.check_call(cmd)


def ensure_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("📦 Установка PyInstaller...")
        run([sys.executable, "-m", "pip", "install", "--upgrade", "pyinstaller"])


def build() -> None:
    ensure_pyinstaller()

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--windowed",
        "--clean",
        "--noconfirm",
        "--name",
        PROJECT_NAME,
    ]

    if Path(ICON_FILE).exists():
        cmd.extend(["--icon", ICON_FILE])

    for src, dst in ADD_DATA:
        src_path = Path(src)
        if src_path.exists():
            cmd.extend(["--add-data", f"{src};{dst}"])

    cmd.append(ENTRY_MODULE)

    print("▶ Сборка EXE...")
    run(cmd)

    print("\n✅ ГОТОВО")
    print(f"📦 dist/{PROJECT_NAME}.exe")


if __name__ == "__main__":
    build()
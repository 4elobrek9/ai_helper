import sys
import subprocess
import os

PROJECT_NAME = "AI_Helper"
ENTRY_FILE = "gui.py"

ADD_DATA = [
    "audio;audio",
    "models;models",
    "config.db;.",
    "memory.json;.",
    "hardmemory.json;.",
    "command.json;.",
    "requirements.txt;.",
    "icon.png;.",
    "app_icon.png;.",
    "nerd_lst.mp3;.",
    "conf.mp3;.",
]

def run(cmd):
    subprocess.check_call(cmd, shell=False)

def ensure_clean_env():
    # УДАЛЯЕМ ВРЕДНЫЙ pathlib
    try:
        import pathlib  # noqa
        print("⚠ Найден pip-пакет pathlib — удаляю")
        run([sys.executable, "-m", "pip", "uninstall", "-y", "pathlib"])
    except Exception:
        pass

def ensure_pyinstaller():
    try:
        import PyInstaller  # noqa
    except ImportError:
        print("📦 Устанавливаю PyInstaller")
        run([sys.executable, "-m", "pip", "install", "--upgrade", "pyinstaller"])

def build():
    ensure_clean_env()
    ensure_pyinstaller()

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--clean",
        "--noconfirm",
        "--name", PROJECT_NAME,
    ]

    for item in ADD_DATA:
        cmd.extend(["--add-data", item])

    cmd.append(ENTRY_FILE)

    print("▶ Сборка exe...")
    run(cmd)

    print("\n✅ ГОТОВО")
    print(f"📦 dist/{PROJECT_NAME}.exe")

if __name__ == "__main__":
    build()

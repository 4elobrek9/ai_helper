import os
import subprocess
import sys

PROJECT_NAME = "AI_Helper"
ENTRY_FILE = "GUI.py"
ICON_FILE = "app_icon.ico" if os.path.exists("app_icon.ico") else "app_icon.png"

ADD_DATA = [
    "audio;audio",
    "models;models",
    "config.db;.",
    "memory.json;.",
    "hardmemory.json;.",
    "requirements.txt;.",
    "icon.png;.",
    "app_icon.png;.",
    "nerd_lst.mp3;.",
    "conf.mp3;.",
]


def run(cmd):
    subprocess.check_call(cmd, shell=False)


def ensure_pyinstaller():
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        run([sys.executable, "-m", "pip", "install", "--upgrade", "pyinstaller"])


def build():
    ensure_pyinstaller()
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile", "--windowed", "--clean", "--noconfirm",
        "--name", PROJECT_NAME,
    ]
    if os.path.exists(ICON_FILE):
        cmd.extend(["--icon", ICON_FILE])
    for item in ADD_DATA:
        if os.path.exists(item.split(";")[0]):
            cmd.extend(["--add-data", item])
    cmd.append(ENTRY_FILE)
    run(cmd)
    print(f"✅ dist/{PROJECT_NAME}.exe")


if __name__ == "__main__":
    build()

import os
import shutil
import sys
from pathlib import Path


def resource_path(name):
    """Return a path to a read-only file bundled with the application."""
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return root / name


def data_path(name):
    """Return a persistent per-user path, migrating files from older installs."""
    base = Path(
        os.environ.get("LOCALAPPDATA")
        or os.environ.get("APPDATA")
        or Path.home() / ".local" / "share"
    )
    target = base / "LumiAI" / name
    target.parent.mkdir(parents=True, exist_ok=True)

    if not target.exists():
        candidates = (Path.cwd() / name, Path(__file__).resolve().parent / name)
        for candidate in candidates:
            if candidate.is_file() and candidate.resolve() != target.resolve():
                shutil.copy2(candidate, target)
                break
    return target

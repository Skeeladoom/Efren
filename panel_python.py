"""Resolve the bundled interpreter without falling back on Lite installations."""
import os
from pathlib import Path
import sys


def bundled_python(root, windowless=False):
    root = Path(root)
    runtime = root / "runtime" / "python"
    portable = runtime / "python.exe"
    if portable.is_file():
        silent = runtime / "pythonw.exe"
        return silent if windowless and silent.is_file() else portable
    if (root / "lite-build.json").is_file():
        raise FileNotFoundError("В сборке Lite отсутствует runtime/python/python.exe. Восстановите комплект Python.")
    return None


def worker_python(root):
    portable = bundled_python(root)
    if portable:
        return portable
    installed = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Python/Python313/python.exe"
    if installed.is_file():
        return installed
    current = Path(sys.executable)
    return current.with_name("python.exe") if current.name.lower() in {"python.exe", "pythonw.exe"} else Path("python.exe")

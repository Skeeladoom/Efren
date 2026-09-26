"""Add the local CPU/DirectML RVC component to a prepared Lite tree."""

import argparse
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENGINE_DIRECTORIES = ("configs", "infer", "i18n")
ENGINE_FILES = ("jarvis_bridge.py",)
TOOL_FILES = ("cuda_graph.py", "file_io.py", "progress.py")
ASSET_DIRECTORIES = ("hubert_base", "rmvpe")


def add_component(destination, source=ROOT):
    destination = Path(destination).resolve()
    source = Path(source).resolve()
    if not (destination / "lite-build.json").is_file():
        raise ValueError("Expected a prepared EFREN Lite directory")
    python = destination / "runtime" / "python" / "python.exe"
    if not python.is_file():
        raise FileNotFoundError("Lite Python runtime is missing")

    requirements = ROOT / "distribution" / "requirements-rvc-cpu.txt"
    subprocess.run([
        str(python), "-m", "pip", "install", "--break-system-packages",
        "--disable-pip-version-check", "--no-input", "--pre", "-r", str(requirements),
    ], check=True)

    # Versioned engine code lives beside this script. Large neural assets stay
    # in the local source checkout and are embedded into the release build.
    engine_source = ROOT / "distribution" / "rvc_engine_template"
    asset_source = source / "rvc_engine" / "assets"
    engine_target = destination / "rvc_engine"
    engine_target.mkdir(parents=True, exist_ok=True)
    for name in ENGINE_FILES:
        shutil.copy2(engine_source / name, engine_target / name)
    for name in ENGINE_DIRECTORIES:
        shutil.copytree(engine_source / name, engine_target / name, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    tools = engine_target / "tools"
    tools.mkdir(exist_ok=True)
    for name in TOOL_FILES:
        shutil.copy2(engine_source / "tools" / name, tools / name)
    assets = engine_target / "assets"
    assets.mkdir(exist_ok=True)
    for name in ASSET_DIRECTORIES:
        shutil.copytree(asset_source / name, assets / name, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns(".cache", "__pycache__", "*.pyc"))

    subprocess.run([str(python), "-c",
                    "import numpy._core.tests._natype, faiss, librosa, parselmouth, scipy.signal, torch_directml, transformers; print('RVC CPU/DirectML dependencies: OK')"],
                   check=True, cwd=destination)
    print("CPU/DirectML RVC component added:", engine_target)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--source", type=Path, default=ROOT)
    args = parser.parse_args()
    add_component(args.destination, args.source)

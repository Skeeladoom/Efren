"""Add a clean CPython runtime to development staging; never copies site packages."""
import argparse
import json
from pathlib import Path
import shutil


def add_python(staging, runtime):
    staging, runtime = Path(staging).resolve(), Path(runtime).resolve()
    if not (staging / "lite-build.json").is_file():
        raise ValueError("Not Lite staging")
    destination = staging / "runtime/python"
    if destination.exists():
        raise FileExistsError(destination)
    files = ["python.exe", "pythonw.exe", "python3.dll", "python312.dll", "vcruntime140.dll", "vcruntime140_1.dll", "LICENSE.txt"]
    for name in files + ["Lib", "DLLs", "tcl"]:
        if not (runtime / name).exists():
            raise FileNotFoundError(runtime / name)
    destination.mkdir(parents=True)
    for name in files:
        shutil.copyfile(runtime / name, destination / name)
    for name in ("Lib", "DLLs", "tcl"):
        shutil.copytree(runtime / name, destination / name,
                        ignore=shutil.ignore_patterns("site-packages", "__pycache__", "*.pyc", "sitecustomize.py", "usercustomize.py"))
    # Carry only pip itself, not arbitrary packages or startup hooks from the host.
    packages = destination / "Lib/site-packages"
    packages.mkdir()
    for path in (runtime / "Lib/site-packages").glob("pip*"):
        if path.name == "pip" or (path.name.startswith("pip-") and path.name.endswith(".dist-info")):
            shutil.copytree(path, packages / path.name)
    (staging / "runtime/python-origin.json").write_text(json.dumps({
        "kind": "development-runtime", "source": "uv-managed CPython 3.12",
        "publishable": False, "dependencies": "Install explicitly; host packages excluded"
    }, indent=2), encoding="utf-8")
    print("Bundled CPython:", destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("staging")
    parser.add_argument("runtime")
    args = parser.parse_args()
    add_python(args.staging, args.runtime)

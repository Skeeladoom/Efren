"""Build the 0.1.7 targeted update without repacking unchanged AI models."""
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "release-lite-clean"
OUTPUT = Path(__file__).resolve().parent / "EFREN-Lite-Patch.zip"
FILES = {
    "apply-lite-patch.ps1", "lite_policy.py", "main.py", "panel_backend.py",
    "router.py", "stt_variants.py", "tools.py", "lite-build.json",
    "panel-wpf/App.cs", "panel-wpf/MainWindow.xaml",
    "panel-wpf/NativePages.cs", "panel-wpf/bin/FridayPanel.exe",
}
PREFIXES = (
    "runtime/python/Lib/site-packages/pymorphy3/",
    "runtime/python/Lib/site-packages/pymorphy3-2.0.6.dist-info/",
    "runtime/python/Lib/site-packages/pymorphy3_dicts_ru/",
    "runtime/python/Lib/site-packages/pymorphy3_dicts_ru-2.4.417150.4580142.dist-info/",
    "runtime/python/Lib/site-packages/dawg_python/",
    "runtime/python/Lib/site-packages/dawg2_python-0.9.0.dist-info/",
)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build():
    selected = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT).as_posix()
        if relative in FILES or relative.startswith(PREFIXES):
            selected.append(path)
    entries = [{"path": p.relative_to(ROOT).as_posix(), "size": p.stat().st_size,
                "sha256": sha256(p)} for p in sorted(selected)]
    manifest = {"format": "EFREN-LITE-PATCH-1", "to_version": "0.1.7", "files": entries}
    with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr("patch-manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for path in selected:
            archive.write(path, path.relative_to(ROOT).as_posix())
    print(OUTPUT, OUTPUT.stat().st_size, sha256(OUTPUT), len(entries))


if __name__ == "__main__":
    build()

"""Build a verified incremental EFREN Lite update from two prepared trees."""
import argparse, hashlib, json, zipfile
from pathlib import Path

PRIVATE = {"config.json", "assistant_names.json", "jarvis_settings.json", "panel_theme.json",
           "macro_phrases.json", "macro_disabled.json", "stt_variants.json", "lite-auth.json"}
PRIVATE_PREFIXES = ("logs/", "backups/", "updates/", "rvc_models/store/", "scenarios/", "сценарии/")

def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""): h.update(block)
    return h.hexdigest()

def build(old, new, output):
    old, new, output = Path(old).resolve(), Path(new).resolve(), Path(output).resolve()
    changed = []
    for path in sorted(p for p in new.rglob("*") if p.is_file()):
        relative = path.relative_to(new).as_posix()
        if relative in PRIVATE or relative.startswith(PRIVATE_PREFIXES): continue
        previous = old / relative
        sha = digest(path)
        if not previous.is_file() or digest(previous) != sha:
            changed.append({"path": relative, "size": path.stat().st_size, "sha256": sha})
    version = json.loads((new / "lite-build.json").read_text(encoding="utf-8"))["version"]
    manifest = {"format": "EFREN-LITE-PATCH-1", "to_version": version, "files": changed}
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr("patch-manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for item in changed: archive.write(new / item["path"], item["path"])
    print(f"Patch {version}: {len(changed)} files, {output.stat().st_size} bytes")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("old", type=Path); parser.add_argument("new", type=Path); parser.add_argument("output", type=Path)
    args = parser.parse_args(); build(args.old, args.new, args.output)

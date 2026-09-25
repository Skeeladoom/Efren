"""Create or verify a SHA-256 manifest for a prepared Lite directory."""
import argparse
import hashlib
from pathlib import Path


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    manifest = root / "manifest.sha256"
    entries = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path != manifest and "logs" not in path.parts:
            entries.append(f"{digest(path)}  {path.relative_to(root).as_posix()}")
    if args.write:
        manifest.write_text("\n".join(entries) + "\n", encoding="utf-8")
        print(f"Manifest written: {manifest}")
        return 0
    if not manifest.is_file():
        print("Manifest not found; run with --write first.")
        return 2
    expected = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if "  " in line:
            digest_value, name = line.split("  ", 1)
            expected[name] = digest_value
    actual = {line.split("  ", 1)[1]: line.split("  ", 1)[0] for line in entries}
    bad = sorted(set(expected) ^ set(actual) | {name for name in expected if name in actual and expected[name] != actual[name]})
    print("Integrity OK" if not bad else "Integrity FAILED: " + ", ".join(bad))
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())

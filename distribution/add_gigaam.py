"""Stage the already tested GigaAM source and checkpoint, never its environment."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def add(staging, source, checkpoint):
    staging, source, checkpoint = map(lambda x: Path(x).resolve(), (staging, source, checkpoint))
    if not (staging / "lite-build.json").exists():
        raise ValueError("Expected Lite staging")
    destination = staging / "runtime/python/Lib/site-packages/gigaam"
    if destination.exists():
        raise FileExistsError(destination)
    if not (source / "gigaam/__init__.py").is_file() or not (source / "LICENSE").is_file() or not checkpoint.is_file():
        raise FileNotFoundError("GigaAM sources, license or checkpoint missing")
    shutil.copytree(source / "gigaam", destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    licenses = staging / "licenses/gigaam"
    licenses.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source / "LICENSE", licenses / "LICENSE")
    target = staging / "models/gigaam/v3_rnnt.ckpt"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        shutil.copyfile(checkpoint, target)
    hashes = {p.relative_to(destination).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in destination.rglob("*") if p.is_file()}
    hashes["v3_rnnt.ckpt"] = hashlib.sha256(target.read_bytes()).hexdigest()
    (licenses / "snapshot-hashes.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")
    print("GigaAM package and model copied into Lite; source hashes recorded.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("staging", "source", "checkpoint"):
        parser.add_argument(name)
    args = parser.parse_args()
    add(args.staging, args.source, args.checkpoint)

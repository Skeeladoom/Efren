"""Refresh allowlisted development sources only; preserve all user/runtime files."""
import argparse
from pathlib import Path
import re
import shutil
from prepare_lite import ROOT, SOURCES


def refresh(destination):
    destination = Path(destination).resolve()
    if destination == ROOT or not (destination / "lite-build.json").is_file():
        raise ValueError("Expected a separate Lite staging directory")
    for name in SOURCES:
        target = destination / name
        if not target.resolve().is_relative_to(destination):
            raise ValueError("Redirected staging path")
        target.parent.mkdir(parents=True, exist_ok=True)
        if name == "control_panel_v0120_JARVIS.py":
            text = (ROOT / name).read_text(encoding="utf-8")
            text, count = re.subn(r'^START_PASSWORD_HASH\s*=.*$', 'START_PASSWORD_HASH = ""  # Owner password excluded', text, flags=re.MULTILINE)
            if count != 1:
                raise ValueError("Expected exactly one legacy password assignment")
            target.write_text(text, encoding="utf-8")
        else:
            shutil.copyfile(ROOT / name, target)
    print("Development sources refreshed; owner password excluded; settings preserved.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination")
    refresh(parser.parse_args().destination)

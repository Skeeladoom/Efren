"""Development-only voice assets. No personal audio, Discord credentials or models."""
import argparse
import json
import os
from pathlib import Path
import shutil


def prepare(staging, piper_source):
    staging, source = Path(staging).resolve(), Path(piper_source).resolve()
    if not (staging / "lite-build.json").is_file():
        raise ValueError("Expected Lite staging")
    target = staging / "runtime/piper"
    files = ("piper.exe", "espeak-ng.dll", "onnxruntime.dll",
             "onnxruntime_providers_shared.dll", "piper_phonemize.dll")
    for name in files + ("ru_RU-ruslan-medium.onnx", "ru_RU-ruslan-medium.onnx.json", "espeak-ng-data"):
        if not (source / name).exists():
            raise FileNotFoundError(source / name)
    target.mkdir(parents=True, exist_ok=True)
    for name in files:
        if not (target / name).exists():
            shutil.copyfile(source / name, target / name)
    if not (target / "espeak-ng-data").exists():
        shutil.copytree(source / "espeak-ng-data", target / "espeak-ng-data")
    voices = staging / "tts_models"
    voices.mkdir(exist_ok=True)
    for name in ("ru_RU-ruslan-medium.onnx", "ru_RU-ruslan-medium.onnx.json"):
        if not (voices / name).exists():
            shutil.copyfile(source / name, voices / name)
    (staging / "runtime/voice-assets.json").write_text(json.dumps({
        "publishable": False, "stt": "GigaAM is staged separately using add_gigaam.py",
        "tts": "ruslan-medium; local Piper copied for development only",
        "pending": "Collect all engine and voice redistribution notices before release"
    }, indent=2), encoding="utf-8")
    print("Voice assets prepared (development only).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("staging")
    parser.add_argument("piper_source")
    args = parser.parse_args()
    prepare(args.staging, args.piper_source)

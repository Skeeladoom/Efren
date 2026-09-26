"""Prepare an isolated, source-only Lite staging tree. NOT a public release.

Never copy personal settings, credentials, logs, models or existing runtimes.
Output must not exist: a repeat build cannot overwrite somebody's settings.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import re

ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    "main.py", "voice.py", "tts.py", "tools.py", "router.py", "memory.py", "gigaam_local.py",
    "local_llm.py", "discord_tools.py", "friday_voice_worker.py",
    "assistant_identity.py", "macro_runner.py", "apple_game_bot.py",
    "panel_backend.py", "panel_features.py", "panel_log_format.py", "panel_python.py", "lite_policy.py", "lite_runtime.py",
    "control_panel_v0120_JARVIS.py", "silero_tts_bridge.py",
    "friday_icon.ico", "panel-wpf/App.cs", "panel-wpf/Appearance.cs",
    "panel-wpf/NativePages.cs", "panel-wpf/MainWindow.xaml", "panel-wpf/build.ps1",
    "sounds/Open.wav", "sounds/Close.wav", "sounds/ClickS.wav",
    "sounds/Change.wav", "sounds/Excellent.wav", "sounds/Block.wav",
)
CONFIG = {
    "edition": "lite", "apps": {
        "notepad": "%WINDIR%\\system32\\notepad.exe",
        "calculator": "%WINDIR%\\system32\\calc.exe",
        "explorer": "%WINDIR%\\explorer.exe",
    }, "wake_words": ["джарвис"],
    "voice_device": None, "voice_device_name": "",
    "tts_device": None, "tts_device_name": "",
    "jarvis_stt_backend": "gigaam-local-cpu",
    "gigaam_model_dir": "models/gigaam", "gigaam_cpu_threads": 2,
    "whisper_language": "ru", "tts_engine": "piper", "tts_enabled": True,
    "piper_exe": "runtime/piper/piper.exe",
    "piper_model": "tts_models/ru_RU-ruslan-medium.onnx",
    "rvc_enabled": False, "rvc_required": False, "rvc_cpu_threads": 4,
    "rvc_root": "rvc_engine", "rvc_python": "runtime/python/python.exe",
    "rvc_timeout_seconds": 60,
}
SETTINGS = {
    "voice_enabled": True, "tts_enabled": True,
    "windows_commands_enabled": True, "discord_commands_enabled": False,
    "friends_voice_enabled": False, "friends_can_use_discord": False,
    "friends_can_use_windows": False, "friends_can_use_qwen": False,
    "qwen_mode": "disabled", "default_browser": "edge",
    "browser_clarification_enabled": True, "ui_sounds_enabled": True,
}


def prepare(destination, source=ROOT):
    destination = Path(destination).resolve()
    source = Path(source).resolve()
    if destination.exists():
        raise FileExistsError("Output already exists; choose a new staging directory")
    # Validate every allowlisted source before writing anything.
    for name in SOURCES:
        candidate = source / name
        if not candidate.is_file() or candidate.is_symlink() or not candidate.resolve().is_relative_to(source):
            raise ValueError("Missing or redirected source: " + name)
    destination.mkdir(parents=True)
    for name in SOURCES:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)
        if name == "control_panel_v0120_JARVIS.py":
            text = target.read_text(encoding="utf-8")
            text = re.sub(r'^START_PASSWORD_HASH\s*=.*$', 'START_PASSWORD_HASH = ""  # Never ship owner credentials', text, flags=re.MULTILINE)
            target.write_text(text, encoding="utf-8")
    for name, data in (("config.json", CONFIG), ("jarvis_settings.json", SETTINGS),
                       ("assistant_names.json", {"jarvis": "Джарвис", "friday": "Пятница"}),
                       ("lite-build.json", {"edition": "lite", "publishable": False})):
        (destination / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (destination / "NOT_A_RELEASE.txt").write_text(
        "DEVELOPMENT STAGING ONLY. Not portable and not ready for distribution.\n"
        "Python runtime, dependencies, voice models and Lite UI isolation are not packaged.\n"
        "Do not upload this folder as a release.\n", encoding="utf-8")
    files = {}
    for path in sorted(destination.rglob("*")):
        if path.is_file():
            files[path.relative_to(destination).as_posix()] = {
                "size": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
    manifest = {"edition": "lite", "publishable": False, "kind": "source-staging", "files": files}
    (destination / "staging-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    result = prepare(args.destination)
    print("Prepared", len(result["files"]), "files. DEVELOPMENT ONLY; not a portable release.")

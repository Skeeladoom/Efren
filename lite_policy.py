"""Capabilities of the development Lite edition, enforced before dispatch."""
from pathlib import Path


def is_lite(root):
    return (Path(root) / "lite-build.json").is_file()


def enforce_settings(settings, lite):
    if lite:
        settings["qwen_mode"] = "disabled"
        for key in ("discord_commands_enabled", "friends_voice_enabled",
                    "friends_can_use_discord", "friends_can_use_windows", "friends_can_use_qwen"):
            settings[key] = False
    return settings


def check_request(request, lite):
    if not lite:
        return
    action = request.get("action")
    allowed = action in {"status", "authenticate", "project", "macros", "jarvis",
                         "console", "favorite", "journal_settings", "diagnostics", "startup", "full_shutdown"}
    if action == "logs":
        allowed = request.get("source") == "jarvis"
    if action == "window":
        allowed = request.get("window") == "chat"
    if action == "setting":
        allowed = request.get("key") in {
            "voice_enabled", "tts_enabled", "windows_commands_enabled",
            "default_browser", "browser_clarification_enabled", "ui_sounds_enabled"}
    if action == "name":
        allowed = request.get("key") == "jarvis"
    # Never expose Discord actions or the legacy full panel through Lite.
    if not allowed:
        raise PermissionError("Эта функция недоступна в текущей сборке Джарвис Lite.")

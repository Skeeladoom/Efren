import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import panel_backend as backend
from lite_runtime import startup_file
from distribution.prepare_lite import SOURCES, SETTINGS


class LiteFeatureTests(unittest.TestCase):
    def test_sounds_packaged_and_default_on(self):
        self.assertTrue(SETTINGS["ui_sounds_enabled"])
        import wave
        root = Path(__file__).resolve().parents[1]
        for name in ("Open", "Close", "ClickS", "Change", "Excellent", "Block"):
            relative = "sounds/" + name + ".wav"
            self.assertIn(relative, SOURCES)
            with wave.open(str(root / relative)) as audio:
                self.assertGreater(audio.getnframes(), 0)

    def test_lite_startup_has_separate_identity(self):
        self.assertNotEqual(startup_file("one"), startup_file("two"))
        self.assertNotEqual(startup_file("one").name, "EFREN_WPF.lnk")

    def test_lite_dispatch_never_calls_discord_for_local_features(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "lite-build.json").write_text("{}")
            with patch.object(backend.panel, "BASE_DIR", root), patch.object(backend.panel, "SETTINGS_FILE", root / "settings.json"), patch.object(backend.panel, "load_settings", return_value={}), patch.object(backend, "bot_action") as bot, patch.object(backend, "jarvis_action") as jarvis, patch.object(backend, "lite_console", None):
                backend.dispatch({"action": "favorite", "operation": "add", "text": "который час"})
                self.assertIn("который час", (root / "settings.json").read_text(encoding="utf-8"))
                result = backend.dispatch({"action": "diagnostics"})
                self.assertIn("ОТСУТСТВУЕТ", result["system"])
                backend.dispatch({"action": "full_shutdown"})
                jarvis.assert_called_once_with("stop")
                bot.assert_not_called()

    def test_console_uses_local_assistant_and_logs_result(self):
        import main
        from voice import VoiceListener
        assistant = MagicMock()
        assistant.handle.return_value = ("answer", "Тестовый ответ")
        with patch.object(backend, "lite_console", assistant), patch.object(main, "speak_answer") as speak, patch.object(VoiceListener, "_write_log") as log:
            result = backend.lite_console_action("который час", "command")
            self.assertEqual(result["result"], "Тестовый ответ")
            assistant.handle.assert_called_once_with("который час")
            speak.assert_called_once()
            log.assert_called_once()

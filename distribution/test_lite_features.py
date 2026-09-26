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
from router import LocalRouter
from stt_variants import normalize_text, read_dictionary, save_selected


class LiteFeatureTests(unittest.TestCase):
    def test_stt_variants_use_word_boundaries_and_preserve_builtin_layer(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stt_variants.json"
            save_selected(path, "дима", ["дима", "диме", "диму"])
            dictionary = read_dictionary(path)
            self.assertEqual(normalize_text("скажи диме привет", dictionary), "скажи дима привет")
            self.assertEqual(normalize_text("диметра рядом", dictionary), "диметра рядом")
        router = LocalRouter(["джарвис"], MagicMock())
        self.assertEqual(router.normalize_stt("аткрой настройки"), "открой настройки")

    def test_computer_power_routes_do_not_capture_jarvis_exit(self):
        router = LocalRouter(["джарвис"], MagicMock())
        self.assertEqual(router.route("выключи компьютер").kind, "computer_shutdown")
        self.assertEqual(router.route("перезагрузи пк").kind, "computer_restart")
        self.assertEqual(router.route("выключи комп").kind, "computer_shutdown")
        self.assertEqual(router.route("выруби пк").kind, "computer_shutdown")
        self.assertEqual(router.route("перезагрузить компьютер").kind, "computer_restart")
        self.assertEqual(router.route("выключись").kind, "exit")
        self.assertEqual(router.route("останови джарвиса").kind, "exit")

    def test_launch_macros_have_open_start_alias_and_close_inverse(self):
        import router as router_module
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scenario = root / "dota.jmacro"
            scenario.write_text(json.dumps({"формат": "JARVIS-MACRO-2", "тип": "launch",
                                            "файл": str(root / "dota2.exe")}, ensure_ascii=False), encoding="utf-8")
            registry = root / "macro_phrases.json"
            registry.write_text(json.dumps({"открой доту": str(scenario)}, ensure_ascii=False), encoding="utf-8")
            disabled = root / "macro_disabled.json"
            disabled.write_text("[]", encoding="utf-8")
            with patch.object(router_module, "MACRO_PHRASES_FILE", registry), \
                 patch.object(router_module, "MACRO_DISABLED_FILE", disabled):
                local = LocalRouter(["джарвис"], MagicMock())
                self.assertEqual(local.route("запусти доту").kind, "macro_phrase")
                self.assertEqual(local.route("закрой доту").kind, "macro_close")

    def test_pymorphy_generates_real_dima_forms(self):
        from stt_variants import generate_forms
        forms = generate_forms("Дима")
        for value in ("Дима", "Димы", "Диме", "Диму", "Димой", "Димою"):
            self.assertIn(value, forms)

    def test_power_tool_uses_windows_shutdown_without_a_shell(self):
        from tools import WindowsTools
        tool = WindowsTools.__new__(WindowsTools)
        with patch("tools.subprocess.Popen") as popen:
            self.assertEqual(tool.computer_power(restart=True), "Перезагружаю компьютер.")
        arguments = popen.call_args.args[0]
        self.assertTrue(str(arguments[0]).lower().endswith("shutdown.exe"))
        self.assertEqual(arguments[1:], ["/r", "/t", "0"])

    def test_voice_status_uses_installed_voice_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            voice = root / "rvc_models/store/test"
            voice.mkdir(parents=True)
            model = voice / "voice.pth"
            model.write_bytes(b"model")
            (voice / "voice.json").write_text(json.dumps({"name": "Тестовый голос"}), encoding="utf-8")
            (root / "config.json").write_text(json.dumps({
                "rvc_enabled": True, "rvc_model": str(model),
                "rvc_device": "cpu", "rvc_cpu_threads": 4,
            }), encoding="utf-8")
            self.assertEqual(backend.jarvis_voice_status(root), "Голос: «Тестовый голос» · CPU, 4 потока")
            (root / "runtime").mkdir()
            (root / "runtime/rvc-status.json").write_text(json.dumps({
                "state": "fallback", "model": "voice",
            }), encoding="utf-8")
            self.assertEqual(backend.jarvis_voice_status(root),
                             "Голос: Piper · «Тестовый голос» не успел обработать реплику")

    def test_gigaam_wake_word_fallback_only_accepts_command_phrases(self):
        from voice import VoiceListener
        listener = VoiceListener.__new__(VoiceListener)
        listener.wake_free_command_fallback = True
        listener.last_partial = ""
        listener._find_wake = MagicMock(return_value=(None, ""))
        listener._already_fast_executed = MagicMock(return_value=False)
        listener._write_log = MagicMock()
        accepted = []
        listener._handle_final("открой блокнот", accepted.append, None)
        listener._handle_final("сегодня хорошая погода", accepted.append, None)
        self.assertEqual(accepted, ["открой блокнот"])

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

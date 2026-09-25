from pathlib import Path
import json
import tempfile
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lite_runtime import authenticate, installation_id, owned_process, jarvis_action


class LiteRuntimeTests(unittest.TestCase):
    def test_first_login_and_password_verification(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(ValueError):
                authenticate(root, "short")
            self.assertFalse((root / "lite-auth.json").exists())
            self.assertTrue(authenticate(root, "sample-pass-123"))
            self.assertTrue(authenticate(root, "sample-pass-123"))
            self.assertFalse(authenticate(root, "wrong-password"))
            self.assertNotIn("sample-pass", (root / "lite-auth.json").read_text())

    def test_damaged_password_never_silently_resets(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "lite-auth.json"
            path.write_text("{}")
            with self.assertRaises(ValueError):
                authenticate(temporary, "new-password")
            self.assertEqual(path.read_text(), "{}")

    def test_installation_identity(self):
        self.assertEqual(installation_id("example"), installation_id("example"))
        self.assertNotEqual(installation_id("example"), installation_id("different"))

    def test_foreign_or_reused_pid_not_owned(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "runtime").mkdir()
            (root / "runtime/lite-process.json").write_text(json.dumps({"pid": 123, "created": 100}))
            import psutil
            with patch.object(psutil, "Process") as factory:
                process = factory.return_value
                process.create_time.return_value = 101
                self.assertIsNone(owned_process(root))
                process.create_time.return_value = 100
                process.exe.return_value = str(root / "other/python.exe")
                self.assertIsNone(owned_process(root))
                self.assertEqual(jarvis_action(root, "stop"), "Готово")
                process.terminate.assert_not_called()

    def test_start_refuses_incomplete_distribution(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(FileNotFoundError):
                jarvis_action(temporary, "start")

    def test_start_and_verified_stop(self):
        import psutil
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            for name in ("runtime/python/python.exe", "main.py", "models/gigaam/v3_rnnt.ckpt",
                         "runtime/piper/piper.exe", "tts_models/ru_RU-ruslan-medium.onnx"):
                file = root / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.touch()
            with patch("lite_runtime.subprocess.Popen") as spawn, patch.object(psutil, "Process") as factory, patch("lite_runtime.time.sleep"):
                child = spawn.return_value
                child.pid = 123
                child.poll.return_value = None
                verified = factory.return_value
                verified.create_time.return_value = 100
                verified.exe.return_value = str(root / "runtime/python/python.exe")
                verified.cmdline.return_value = [str(root / "runtime/python/python.exe"), "-u", str(root / "main.py"), "--resident"]
                self.assertIn("Процесс запущен", jarvis_action(root, "start"))
                self.assertEqual(spawn.call_args.kwargs["cwd"], root)
                self.assertEqual(spawn.call_args.args[0], verified.cmdline.return_value)
                jarvis_action(root, "start")
                spawn.assert_called_once()
                jarvis_action(root, "stop")
                verified.terminate.assert_called_once()
                verified.wait.assert_called_once()
                self.assertFalse((root / "runtime/lite-process.json").exists())

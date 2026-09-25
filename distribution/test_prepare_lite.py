import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from prepare_lite import prepare, SOURCES


class PreparationTests(unittest.TestCase):
    def test_allowlist_clean_settings_hashes_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            for name in SOURCES:
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("test source", encoding="utf-8")
            (source / "control_panel_v0120_JARVIS.py").write_text('START_PASSWORD_HASH = "PRIVATE_MARKER"\n', encoding="utf-8")
            for name in ("config.json", "jarvis_settings.json", ".env", "memory.json", "panel_theme.json"):
                (source / name).write_text("PRIVATE_MARKER", encoding="utf-8")
            output = root / "lite"
            manifest = prepare(output, source)
            self.assertFalse(manifest["publishable"])
            self.assertEqual(len(manifest["files"]), len(SOURCES) + 5)
            for name, entry in manifest["files"].items():
                data = (output / name).read_bytes()
                self.assertNotIn(b"PRIVATE_MARKER", data)
                self.assertEqual(hashlib.sha256(data).hexdigest(), entry["sha256"])
            self.assertFalse((output / ".env").exists())
            self.assertFalse((output / "memory.json").exists())
            settings = json.loads((output / "jarvis_settings.json").read_text())
            self.assertEqual(settings["qwen_mode"], "disabled")
            self.assertFalse(settings["discord_commands_enabled"])
            config = json.loads((output / "config.json").read_text())
            self.assertFalse(config["rvc_enabled"])
            self.assertIsNone(config["voice_device"])
            with self.assertRaises(FileExistsError):
                prepare(output, source)

    def test_missing_input_leaves_no_partial_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(ValueError):
                prepare(root / "output", root)
            self.assertFalse((root / "output").exists())


if __name__ == "__main__":
    unittest.main()

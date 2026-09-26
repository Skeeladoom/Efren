import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from make_lite_patch import build


class LitePatchTests(unittest.TestCase):
    def test_patch_replaces_only_changed_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old, new, installed = root / "old", root / "new", root / "installed"
            for tree in (old, new, installed):
                (tree / "panel-wpf/bin").mkdir(parents=True)
                (tree / "app.py").write_text("old", encoding="utf-8")
                (tree / "config.json").write_text('{"personal":true}', encoding="utf-8")
                (tree / "lite-build.json").write_text(json.dumps({"version": "0.1.7"}), encoding="utf-8")
                shutil.copyfile(Path(r"C:\Windows\System32\where.exe"), tree / "panel-wpf/bin/FridayPanel.exe")
            (new / "app.py").write_text("new", encoding="utf-8")
            (new / "config.json").write_text('{"personal":false}', encoding="utf-8")
            package = root / "EFREN-Lite-Patch.zip"
            build(old, new, package)
            result = subprocess.run([
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                str(Path(__file__).resolve().parents[1] / "apply-lite-patch.ps1"),
                "-Package", str(package), "-InstallDir", str(installed), "-WaitPid", "999999", "-NoRestart",
            ], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((installed / "app.py").read_text(encoding="utf-8"), "new")
            self.assertEqual((installed / "config.json").read_text(encoding="utf-8"), '{"personal":true}')


if __name__ == "__main__":
    unittest.main()

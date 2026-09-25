from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from panel_python import bundled_python, worker_python


class InterpreterTests(unittest.TestCase):
    def test_portable_precedence_and_strict_lite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assertIsNone(bundled_python(root))
            (root / "lite-build.json").write_text("{}")
            with self.assertRaises(FileNotFoundError):
                worker_python(root)
            runtime = root / "runtime/python"
            runtime.mkdir(parents=True)
            (runtime / "python.exe").touch()
            self.assertEqual(worker_python(root), runtime / "python.exe")
            self.assertEqual(bundled_python(root, True), runtime / "python.exe")
            (runtime / "pythonw.exe").touch()
            self.assertEqual(bundled_python(root, True), runtime / "pythonw.exe")

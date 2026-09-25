import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gigaam_local import LocalGigaAM


class LocalGigaAMTests(unittest.TestCase):
    def test_missing_model_fails_before_runtime_import_or_download(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(FileNotFoundError, "v3_rnnt.ckpt"):
                LocalGigaAM(directory, {})

    def test_empty_and_oversized_audio_do_not_run_model(self):
        recognizer = LocalGigaAM.__new__(LocalGigaAM)
        self.assertEqual(recognizer.transcribe([]), "")
        with self.assertRaises(ValueError):
            recognizer.transcribe(range(25 * 16000 + 1))

"""Exercise real VoiceListener PCM path in staged CPU-only Python, without mic."""
import importlib.abc
import json
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch

root = Path(sys.argv[1]).resolve()
samples = Path(sys.argv[2]).resolve()
sys.path.insert(0, str(root))
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["PATH"] = str(Path(os.environ["SYSTEMROOT"]) / "System32")


class BlockImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"ollama", "friday_voice_worker", "faster_whisper"}:
            raise ImportError("Not available in Lite: " + fullname)


sys.meta_path.insert(0, BlockImports())
import numpy as np
import soundfile as sf
import torch
import gigaam
import voice

assert torch.version.cuda is None, "Expected CPU-only torch distribution"
assert Path(gigaam.__file__).resolve().is_relative_to(root)
config = json.loads((root / "config.json").read_text(encoding="utf-8"))
started = time.perf_counter()
with patch.object(voice.sd, "query_devices", return_value={"name": "test", "default_samplerate": 22050}):
    listener = voice.VoiceListener(config, ["джарвис"])
assert listener.uses_local_gigaam and not listener.uses_shared_stt
report = {"backend": "gigaam-local-cpu", "torch": torch.__version__,
          "load_seconds": round(time.perf_counter() - started, 3), "results": []}
for path in sorted(samples.glob("*.wav")):
    audio, rate = sf.read(path, dtype="int16")
    assert audio.ndim == 1
    listener.samplerate = rate
    started = time.perf_counter()
    text = listener._transcribe_pcm(audio.tobytes())
    if not text:
        raise AssertionError("Empty transcription: " + path.name)
    item = {"file": path.name, "text": text, "seconds": round(time.perf_counter() - started, 3)}
    report["results"].append(item)
    print(json.dumps(item, ensure_ascii=True), flush=True)
(root / "runtime/gigaam-integration-test.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print("PASS: actual Lite PCM pipeline, CPU-only torch, local model, no shared server/Whisper/ffmpeg.")

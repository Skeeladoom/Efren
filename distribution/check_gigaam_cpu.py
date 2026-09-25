"""Benchmark existing GigaAM on listening samples, CPU only; no server/actions."""
import json
import os
from pathlib import Path
import time
import wave

os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["OMP_NUM_THREADS"] = "2"
os.environ["MKL_NUM_THREADS"] = "2"
import torch
import gigaam

root = Path(__file__).resolve().parents[1]
samples = root / "runtime/lite-listening"
checkpoint = Path(r"F:\Efrun\models\gigaam\v3_rnnt.ckpt")
if not checkpoint.is_file():
    raise FileNotFoundError(checkpoint)
torch.set_num_threads(2)
torch.set_num_interop_threads(1)
started = time.perf_counter()
model = gigaam.load_model("v3_rnnt", device="cpu", fp16_encoder=False,
                          use_flash=False, download_root=str(checkpoint.parent))
assert next(model.parameters()).device.type == "cpu"
report = {"model": "v3_rnnt", "device": "cpu", "threads": 2,
          "load_seconds": round(time.perf_counter() - started, 3), "results": []}
print("Loaded on CPU in", report["load_seconds"], "seconds", flush=True)
for path in sorted(samples.glob("*.wav")):
    with wave.open(str(path)) as audio:
        duration = audio.getnframes() / audio.getframerate()
    timings, transcripts = [], []
    for repeat in range(2):
        started = time.perf_counter()
        with torch.inference_mode():
            text = model.transcribe(str(path))
        timings.append(round(time.perf_counter() - started, 3))
        transcripts.append(str(getattr(text, "text", text) or "").strip())
    item = {"file": path.name, "audio_seconds": round(duration, 3),
            "seconds": timings, "texts": transcripts}
    report["results"].append(item)
    print(json.dumps(item, ensure_ascii=True), flush=True)
    (samples / "gigaam-cpu-results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print("DONE", flush=True)

"""Generate neutral test speech and transcribe locally. No playback or actions."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import wave

root = Path(sys.argv[1]).resolve()
if not (root / "lite-build.json").exists():
    raise ValueError("Expected Lite staging")
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.chdir(root)
sys.path.insert(0, str(root))
from faster_whisper import WhisperModel

phrase = "Джарвис, открой настройки. Сейчас проверяется голосовой помощник."
wav = root / "runtime/lite-voice-test.wav"
start = time.perf_counter()
result = subprocess.run([str(root / "runtime/piper/piper.exe"),
                         "--model", str(root / "tts_models/ru_RU-ruslan-medium.onnx"),
                         "--output_file", str(wav)], input=phrase + "\n", text=True,
                        encoding="utf-8", capture_output=True, timeout=90,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
if result.returncode:
    raise RuntimeError(result.stderr)
tts_seconds = time.perf_counter() - start
with wave.open(str(wav)) as stream:
    duration = stream.getnframes() / stream.getframerate()
    assert duration > 1
start = time.perf_counter()
model = WhisperModel(str(root / "models/whisper-base"), device="cpu", compute_type="int8",
                     cpu_threads=2, num_workers=1, local_files_only=True)
load_seconds = time.perf_counter() - start
start = time.perf_counter()
segments, _ = model.transcribe(str(wav), language="ru", beam_size=1, vad_filter=False)
text = " ".join(segment.text.strip() for segment in segments)
report = {"input": phrase, "recognized": text, "audio_seconds": round(duration, 2),
          "tts_seconds": round(tts_seconds, 2), "stt_load_seconds": round(load_seconds, 2),
          "stt_seconds": round(time.perf_counter() - start, 2),
          "device": "cpu", "threads": 2, "playback": False, "commands_executed": False}
(root / "runtime/voice-test.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
if not text.strip():
    raise AssertionError("No transcription")
print(json.dumps(report, ensure_ascii=True))

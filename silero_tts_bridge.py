"""Persistent CPU-only Silero TTS bridge used before RVC conversion."""

import json
import os
import sys
import time
import wave
from pathlib import Path

import torch


BRIDGE_VERSION = "SILERO-TTS-BRIDGE-v0.1.0"
PREFIX = "SILERO_TTS:"


def reply(payload):
    print(PREFIX + json.dumps(payload, ensure_ascii=False), flush=True)


def write_wav(path, audio, sample_rate):
    # RVC's pitch extractor can stall on very short Silero clips. Padding is
    # removed after conversion by LocalTTS, so Discord never hears it.
    minimum_samples = int(sample_rate * 3.2)
    if audio.numel() < minimum_samples:
        audio = torch.nn.functional.pad(audio, (0, minimum_samples - audio.numel()))
    samples = (
        audio.detach()
        .cpu()
        .clamp(-1, 1)
        .mul(32767)
        .to(torch.int16)
        .numpy()
        .tobytes()
    )
    output = Path(path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(samples)


def main():
    model_path = Path(sys.argv[1]).resolve()
    speaker = str(sys.argv[2])
    sample_rate = int(sys.argv[3])
    threads = max(1, min(8, int(sys.argv[4])))

    # Silero stays on the CPU so it cannot compete with GigaAM and RVC for
    # the GTX 1060. These variables also prevent CUDA from being initialized.
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    torch.set_num_threads(threads)
    torch.set_num_interop_threads(1)
    torch._C._jit_set_profiling_mode(False)

    model = torch.package.PackageImporter(str(model_path)).load_pickle(
        "tts_models",
        "model",
    )
    model.to(torch.device("cpu"))

    # Warm both the synthesizer and the Russian accent/yo normalizer before
    # reporting readiness. The first real Friday phrase then avoids the lazy
    # initialization pause seen during the A/B test.
    model.apply_tts(
        text="Пятница готова.",
        speaker=speaker,
        sample_rate=sample_rate,
        put_accent=True,
        put_yo=True,
    )
    reply({
        "status": "ready",
        "version": BRIDGE_VERSION,
        "device": "cpu",
        "threads": threads,
        "speaker": speaker,
        "sample_rate": sample_rate,
    })

    for line in sys.stdin:
        try:
            request = json.loads(line)
            text = str(request.get("text", "")).strip()
            output = Path(request["output"]).resolve()
            if not text:
                raise ValueError("empty text")
            started = time.perf_counter()
            audio = model.apply_tts(
                text=text,
                speaker=speaker,
                sample_rate=sample_rate,
                put_accent=True,
                put_yo=True,
            )
            write_wav(output, audio, sample_rate)
            reply({
                "status": "ready",
                "output": str(output),
                "render_ms": round((time.perf_counter() - started) * 1000.0),
            })
        except Exception as exc:
            reply({"status": "error", "error": f"{type(exc).__name__}: {exc}"})


if __name__ == "__main__":
    main()

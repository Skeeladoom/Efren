"""Постоянный локальный преобразователь голоса JARVIS через RVC."""

RVC_BRIDGE_VERSION = "JARVIS-RVC-BRIDGE-v0.1.4-ARTICULATION"

import json
import os
import sys
from pathlib import Path

CPU_THREADS = max(1, min(32, int(sys.argv[3]))) if len(sys.argv) > 3 else 4
REQUESTED_DEVICE = str(sys.argv[4]).lower() if len(sys.argv) > 4 else "auto"
if REQUESTED_DEVICE == "cpu":
    os.environ["RVC_FORCE_CPU"] = "1"
os.environ.setdefault("OMP_NUM_THREADS", str(CPU_THREADS))
os.environ.setdefault("MKL_NUM_THREADS", str(CPU_THREADS))

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("weight_root", str(ROOT / "assets" / "weights"))
os.environ.setdefault("index_root", str(ROOT / "logs"))
os.environ.setdefault("outside_index_root", str(ROOT / "assets" / "indices"))
os.environ.setdefault("rmvpe_root", str(ROOT / "assets" / "rmvpe"))

import soundfile as sf
import torch
from configs.config import Config
from infer.vc.modules import VC

PREFIX = "JARVIS_RVC:"


def reply(data):
    print(PREFIX + json.dumps(data, ensure_ascii=False), flush=True)


def main():
    torch.set_num_threads(CPU_THREADS)
    torch.set_num_interop_threads(1)
    model = Path(sys.argv[1]).resolve()
    index = Path(sys.argv[2]).resolve()
    os.environ["weight_root"] = str(model.parent)

    saved = sys.argv[:]
    sys.argv = [sys.argv[0]]
    try:
        config = Config()
    finally:
        sys.argv = saved

    converter = VC(config)
    converter.get_vc(model.name)
    reply({
        "status": "ready",
        "device": str(config.device),
        "version": RVC_BRIDGE_VERSION,
        "threads": CPU_THREADS,
        "requested_device": REQUESTED_DEVICE,
    })

    for line in sys.stdin:
        try:
            request = json.loads(line)
            source = str(Path(request["input"]).resolve())
            output = Path(request["output"]).resolve()
            pitch_method = str(request.get("method", "rmvpe")).lower().strip()
            if pitch_method not in {"pm", "harvest", "crepe", "rmvpe"}:
                pitch_method = "rmvpe"
            status, result = converter.vc_single(
                int(request.get("speaker", 0)), source,
                int(request.get("pitch", 0)), pitch_method, str(index),
                float(request.get("index_rate", 0.45)),
                max(0, min(7, int(request.get("filter_radius", 3)))),
                1.0,
                max(0.0, min(0.5, float(request.get("protect", 0.28)))),
            )
            if not result or result[0] is None or result[1] is None:
                raise RuntimeError(str(status))
            sf.write(str(output), result[1], result[0])
            reply({"status": "ready", "output": str(output)})
        except Exception as exc:
            reply({"status": "error", "error": str(exc)})


if __name__ == "__main__":
    main()

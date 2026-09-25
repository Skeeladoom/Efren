"""Lite dependency/initialization test. No microphone, model download or speech."""
import importlib.abc
import json
from pathlib import Path
import sys
from unittest.mock import patch, MagicMock

root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))


class ForbiddenImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"ollama", "local_llm", "friday_voice_worker", "faster_whisper"}:
            raise AssertionError("Lite unexpectedly imported " + fullname)


sys.meta_path.insert(0, ForbiddenImports())
import voice
import main

config = json.loads((root / "config.json").read_text(encoding="utf-8"))
with patch("gigaam_local.LocalGigaAM") as model, patch.object(voice.sd, "query_devices", return_value={"default_samplerate": 16000, "name": "test"}):
    listener = voice.VoiceListener(config, ["джарвис"])
    assert not listener.uses_shared_stt
    assert listener.uses_local_gigaam
    assert model.call_args.args[1]["gigaam_cpu_threads"] == 2

# Avoid TTS initialization and all OS actions; test settings and absence of LLM.
with patch.object(main, "LocalTTS", return_value=MagicMock()), patch.object(main, "WindowsTools"), patch.object(main, "Memory"):
    jarvis = main.Jarvis()
    assert jarvis.llm is None
    assert jarvis.runtime_settings["qwen_mode"] == "disabled"
    assert jarvis.runtime_settings["discord_commands_enabled"] is False
print("PASS: Lite imports without Ollama/Whisper/Friday worker; GigaAM initialization (mocked); Qwen disabled.")

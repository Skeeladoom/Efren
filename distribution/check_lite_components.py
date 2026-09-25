"""Initialize real assistant, synthesize and recognize without playback/mic/actions."""
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

root = Path(sys.argv[1]).resolve()
os.chdir(root)
sys.path.insert(0, str(root))
os.environ["PATH"] = str(Path(os.environ["SYSTEMROOT"]) / "System32")
import main
from tts import LocalTTS
import soundfile as sf
from voice import VoiceListener

with patch.object(main, "LocalTTS", side_effect=lambda config: LocalTTS(config, playback_enabled=False)):
    assistant = main.Jarvis()
assert assistant.llm is None and assistant.tts.enabled
assert not assistant.tts.rvc_enabled
wav = root / "runtime/lite-components-test.wav"
assistant.tts.render_to_file("Джарвис, открой настройки.", str(wav))
audio, rate = sf.read(wav, dtype="int16")
with patch("voice.sd.query_devices", return_value={"default_samplerate": rate, "name": "test"}):
    listener = VoiceListener(assistant.config, ["джарвис"])
text = listener._transcribe_pcm(audio.tobytes())
assert "настройки" in text, text
assert assistant._execute_route(main.Route("discord_bot_stop", {})) == "Эта команда недоступна в Джарвис Lite."
assistant.tts.stop()
print("PASS: real Jarvis initialization + Piper synthesis + GigaAM recognition + Discord execution guard; no mic/playback/commands.")

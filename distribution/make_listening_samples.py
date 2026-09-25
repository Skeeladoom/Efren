"""Make listening samples only; never execute or recognize spoken commands."""
from pathlib import Path
import shutil
import subprocess
import wave

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "distribution/staging-lite-002"
OUTPUT = ROOT / "runtime/lite-listening"
PHRASES = [
    ("02_settings.wav", "Джарвис, открой настройки."),
    ("03_game.wav", "Джарвис, запусти Доту."),
    ("04_volume.wav", "Джарвис, сделай громкость тише."),
    ("05_normal_speech.wav", "Сегодня хорошая погода. Через пять минут я вернусь к компьютеру."),
    ("06_yo.wav", "Ёжик идёт вперёд. Всё готово. Включи ещё одну песню."),
]


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    original = STAGING / "runtime/lite-voice-test.wav"
    first = OUTPUT / "01_original_test.wav"
    if not first.exists():
        shutil.copyfile(original, first)
    descriptions = ["Piper / Ruslan medium. Без RVC, изменения скорости и усиления.",
                    "01_original_test.wav — Джарвис, открой настройки. Сейчас проверяется голосовой помощник.",
                    "Первый файл — точная копия предыдущего теста, не новая генерация."]
    for filename, phrase in PHRASES:
        target = OUTPUT / filename
        if not target.exists():
            result = subprocess.run([
                str(STAGING / "runtime/piper/piper.exe"), "--model",
                str(STAGING / "tts_models/ru_RU-ruslan-medium.onnx"),
                "--output_file", str(target)
            ], input=phrase + "\n", text=True, encoding="utf-8", capture_output=True,
                timeout=90, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if result.returncode:
                raise RuntimeError(result.stderr)
        descriptions.append(filename + " — " + phrase)
    for target in sorted(OUTPUT.glob("*.wav")):
        with wave.open(str(target)) as audio:
            assert audio.getnframes() > 0
            print(target.name, round(audio.getnframes() / audio.getframerate(), 2), "seconds")
    (OUTPUT / "Тексты записей.txt").write_text("\n\n".join(descriptions), encoding="utf-8-sig")


if __name__ == "__main__":
    main()

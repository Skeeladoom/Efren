import json
import os
import queue
import re
import subprocess
import tempfile
import threading
import time
import wave
from array import array
from pathlib import Path

TTS_CODE_VERSION = "JARVIS-TTS-v0.8.1-SILERO-SHORT-CLIP-PADDING"

# Меняем только текст, который идёт В ГОЛОС.
# В терминале ответ остаётся оригинальным.
TTS_WORDS = {
    "discord": "дискорд",
    "chrome": "хром",
    "google": "гугл",
    "youtube": "ютуб",
    "steam": "стим",
    "windows": "виндоус",
    "python": "пайтон",
    "piper": "пайпер",
    "qwen": "квэн",
    "ollama": "оллама",
    "efren": "ефрен",
    "jarvis": "джарвис",
    "github": "гитхаб",
    "telegram": "телеграм",
    "spotify": "спотифай",
    "twitch": "твич",
    "minecraft": "майнкрафт",
    "roblox": "роблокс",
    "dota": "дота",
    "steamvr": "стим ви ар",
    "nvidia": "энвидиа",
    "amd": "эй эм ди",
    "cpu": "си пи ю",
    "gpu": "джи пи ю",
    "ram": "рэм",
    "fps": "эф пи эс",
    "url": "ю эр эл",
    "api": "эй пи ай",
    "vpn": "ви пи эн",
    "usb": "ю эс би",
    "html": "эйч ти эм эл",
    "css": "си эс эс",
    "json": "джейсон",
    "vs": "ви эс",
    "code": "код",
}

TRANSLIT = {
    "a": "а", "b": "б", "c": "к", "d": "д", "e": "е", "f": "ф",
    "g": "г", "h": "х", "i": "и", "j": "дж", "k": "к", "l": "л",
    "m": "м", "n": "н", "o": "о", "p": "п", "q": "к", "r": "р",
    "s": "с", "t": "т", "u": "у", "v": "в", "w": "в", "x": "кс",
    "y": "й", "z": "з",
}


def _transliterate_latin(word: str) -> str:
    low = word.lower()

    if low in TTS_WORDS:
        return TTS_WORDS[low]

    chunks = (
        ("tion", "шн"),
        ("sh", "ш"),
        ("ch", "ч"),
        ("th", "т"),
        ("ph", "ф"),
        ("ck", "к"),
        ("ee", "и"),
        ("oo", "у"),
    )

    result = low
    placeholders = {}

    for index, (latin, cyr) in enumerate(chunks):
        marker = f"§{index}§"
        if latin in result:
            result = result.replace(latin, marker)
            placeholders[marker] = cyr

    out = []
    i = 0

    while i < len(result):
        if result[i] == "§":
            end = result.find("§", i + 1)
            if end != -1:
                marker = result[i:end + 1]
                if marker in placeholders:
                    out.append(placeholders[marker])
                    i = end + 1
                    continue

        out.append(TRANSLIT.get(result[i], result[i]))
        i += 1

    return "".join(out)


def prepare_for_tts(text: str) -> str:
    text = str(text or "").strip()

    text = re.sub(
        r"\bVS\s+Code\b",
        "ви эс код",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\bGoogle\s+Chrome\b",
        "гугл хром",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\b[A-Za-z][A-Za-z0-9_-]*\b",
        lambda m: _transliterate_latin(m.group(0)),
        text,
    )

    return text


class LocalTTS:
    def __init__(self, config, playback_enabled=True):
        self.enabled = bool(config.get("tts_enabled", True))
        self.playback_enabled = bool(playback_enabled)
        self.tts_engine = str(config.get("tts_engine", "piper")).strip().lower()
        if self.tts_engine not in {"piper", "silero"}:
            self.tts_engine = "piper"

        self.piper_exe = Path(
            config.get(
                "piper_exe",
                r"F:\Efrun\piper\piper.exe",
            )
        )

        self.model = Path(
            config.get(
                "piper_model",
                r"F:\Efrun\piper\ru_RU-ruslan-medium.onnx",
            )
        )

        self.config_path = Path(str(self.model) + ".json")

        self.silero_python = Path(
            config.get(
                "silero_tts_python",
                r"F:\Efrun\gigaam_env\Scripts\python.exe",
            )
        )
        self.silero_bridge_path = Path(
            config.get(
                "silero_tts_bridge",
                r"F:\EFREN_v0.4_Local\silero_tts_bridge.py",
            )
        )
        self.silero_model = Path(
            config.get(
                "silero_tts_model",
                r"F:\EFREN_v0.4_Local\tts_models\silero\v4_ru.pt",
            )
        )
        self.silero_speaker = str(config.get("silero_tts_speaker", "aidar"))
        self.silero_sample_rate = int(config.get("silero_tts_sample_rate", 24000))
        self.silero_threads = max(1, min(8, int(config.get("silero_tts_threads", 4))))
        self.silero_timeout = max(3.0, float(config.get("silero_tts_timeout_seconds", 15.0)))
        self.silero_bridge = None

        self.length_scale = float(
            config.get("tts_length_scale", 1.0)
        )

        self.noise_scale = float(
            config.get("tts_noise_scale", 0.667)
        )

        self.noise_w = float(
            config.get("tts_noise_w", 0.8)
        )

        # Куда отправляется голос JARVIS.
        #
        # У тебя:
        # 18 = Voicemeeter AUX Input, MME
        #
        # Лучше задавать через config.json:
        # "tts_device": 18
        self.tts_device = config.get("tts_device", 13)
        self.tts_device_name = str(config.get("tts_device_name", "Voicemeeter Input"))

        self.rvc_enabled = bool(config.get("rvc_enabled", True))
        self.rvc_root = Path(config.get("rvc_root", r"F:\EFREN_v0.4_Local\rvc_engine"))
        self.rvc_python = Path(config.get("rvc_python", r"F:\EFREN_v0.4_Local\rvc_env\Scripts\python.exe"))
        self.rvc_model = Path(config.get("rvc_model", r"F:\EFREN_v0.4_Local\rvc_models\oguzok\MaximLavrov.pth"))
        self.rvc_index = Path(config.get("rvc_index", r"F:\EFREN_v0.4_Local\rvc_models\oguzok\added_IVF166_Flat_nprobe_1_MaximLavrov_v2.index"))
        self.rvc_f0_method = str(config.get("rvc_f0_method", "rmvpe")).lower().strip()
        self.rvc_index_rate = max(0.0, min(1.0, float(config.get("rvc_index_rate", 0.45))))
        # RVC supports protect only in the 0..0.5 range. Values above 0.5
        # silently disable consonant protection inside the inference pipeline.
        self.rvc_protect = max(0.0, min(0.5, float(config.get("rvc_protect", 0.28))))
        self.rvc_filter_radius = max(0, min(7, int(config.get("rvc_filter_radius", 3))))
        # Voice conversion is optional. Never hold spoken feedback for minutes
        # when a DirectML driver or an unsupported model stalls.
        self.rvc_timeout = max(3.0, min(12.0, float(config.get("rvc_timeout_seconds", 10.0))))
        self.rvc_cpu_threads = max(1, min(32, int(config.get("rvc_cpu_threads", 4))))
        self.rvc_device = str(config.get("rvc_device", "auto")).lower().strip()
        if self.rvc_device not in {"auto", "cpu", "directml"}:
            self.rvc_device = "auto"
        self.rvc_required = bool(config.get("rvc_required", False))
        self.last_render_used_rvc = False
        self.last_render_metrics = {}
        self.last_rvc_metrics = {}
        self.rvc_bridge = None

        self.queue = queue.Queue()
        self.thread = None
        self._render_lock = threading.Lock()

        if not self.enabled:
            return

        missing = []

        if self.tts_engine == "silero":
            for path in (
                self.silero_python,
                self.silero_bridge_path,
                self.silero_model,
            ):
                if not path.exists():
                    missing.append(str(path))
        else:
            if not self.piper_exe.exists():
                missing.append(str(self.piper_exe))

            if not self.model.exists():
                missing.append(str(self.model))

            if not self.config_path.exists():
                missing.append(str(self.config_path))

        if missing:
            print(f"[TTS] Базовый движок {self.tts_engine} пока не готов.")
            print("[TTS] Не найдены:")

            for item in missing:
                print("      ", item)

            self.enabled = False
            return

        if self.playback_enabled:
            # Рендеру Пятницы звуковая карта не нужна: готовый WAV забирает
            # Discord-бот и воспроизводит прямо в голосовом канале.
            try:
                import sounddevice
                import soundfile
            except ImportError as exc:
                print(f"[TTS] Ошибка импорта библиотек воспроизведения: {exc}")
                self.enabled = False
                return

            self.tts_device = self._resolve_output_device(sounddevice)
            self.thread = threading.Thread(
                target=self._worker,
                daemon=True,
            )
            self.thread.start()

        try:
            # Load the GPU model first. On the GTX 1060 its cold start is the
            # most timing-sensitive part; the CPU-only Silero warm-up must not
            # make RVC miss its readiness deadline.
            self._start_rvc()
            if self.tts_engine == "silero":
                self._start_silero()
        except Exception:
            self._stop_silero_bridge()
            self._stop_rvc_bridge()
            raise

        if self.tts_engine == "silero":
            print(
                f"[TTS] Silero готов: {self.silero_model.name} / "
                f"{self.silero_speaker} / CPU {self.silero_threads} потока"
            )
        else:
            print(f"[TTS] Piper готов: {self.model.name}")

        if self.playback_enabled:
            print(
                f"[TTS] Выход: устройство {self.tts_device} "
                f"({self.tts_device_name})"
            )

    def _resolve_output_device(self, sounddevice):
        wanted = self.tts_device_name.casefold().strip()
        candidates = []
        for index, device in enumerate(sounddevice.query_devices()):
            name = str(device.get("name", ""))
            if device.get("max_output_channels", 0) > 0 and wanted in name.casefold():
                host = sounddevice.query_hostapis(device["hostapi"])["name"]
                priority = 0 if host == "MME" else 1
                if "aux" in name.casefold() or re.search(r"\bin\s+\d", name.casefold()):
                    priority += 10
                candidates.append((priority, index))
        return min(candidates)[1] if candidates else self.tts_device

    def _start_silero(self):
        required = (
            self.silero_python,
            self.silero_bridge_path,
            self.silero_model,
        )
        if not all(path.exists() for path in required):
            raise RuntimeError("Не найдены файлы локального Silero TTS")
        environment = os.environ.copy()
        environment.update(
            PYTHONUTF8="1",
            PYTHONIOENCODING="utf-8",
            CUDA_VISIBLE_DEVICES="",
        )
        self.silero_bridge = subprocess.Popen(
            [
                str(self.silero_python),
                "-u",
                str(self.silero_bridge_path),
                str(self.silero_model),
                self.silero_speaker,
                str(self.silero_sample_rate),
                str(self.silero_threads),
            ],
            cwd=str(self.silero_bridge_path.parent),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            env=environment,
        )
        print(
            f"[TTS] Загружается Silero на CPU: {self.silero_model.name} / "
            f"{self.silero_threads} потока"
        )
        ready = self._read_silero_reply(max(90.0, self.silero_timeout))
        if not ready or ready.get("status") != "ready":
            self._stop_silero_bridge()
            raise RuntimeError("Silero-мост не подтвердил готовность")

    def _read_silero_reply(self, timeout):
        bridge = self.silero_bridge
        if not bridge or not bridge.stdout:
            return None
        replies = queue.Queue(maxsize=1)

        def read_reply():
            try:
                for line in bridge.stdout:
                    if line.startswith("SILERO_TTS:"):
                        replies.put(
                            json.loads(line.removeprefix("SILERO_TTS:")),
                            block=False,
                        )
                        return
                replies.put(None, block=False)
            except Exception:
                try:
                    replies.put(None, block=False)
                except queue.Full:
                    pass

        threading.Thread(
            target=read_reply,
            name="SileroReplyReader",
            daemon=True,
        ).start()
        try:
            return replies.get(timeout=max(3.0, timeout))
        except queue.Empty:
            return None

    def _render_silero(self, text, output):
        recovery_ms = 0.0
        if not self.silero_bridge or self.silero_bridge.poll() is not None:
            recovery_started = time.perf_counter()
            self._stop_silero_bridge()
            self._start_silero()
            recovery_ms = (time.perf_counter() - recovery_started) * 1000.0
        request = {"text": text, "output": str(output)}
        started = time.perf_counter()
        try:
            self.silero_bridge.stdin.write(
                json.dumps(request, ensure_ascii=False) + "\n"
            )
            self.silero_bridge.stdin.flush()
        except (BrokenPipeError, OSError, ValueError) as exc:
            raise RuntimeError(f"Silero-мост недоступен: {exc}") from exc
        answer = self._read_silero_reply(self.silero_timeout)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if answer is None:
            self._stop_silero_bridge()
            raise RuntimeError(
                f"Silero не ответил за {self.silero_timeout:.1f} с"
            )
        if answer.get("status") == "error":
            raise RuntimeError(f"Silero: {answer.get('error')}")
        if not output.is_file() or output.stat().st_size <= 44:
            raise RuntimeError("Silero не создал корректный WAV-файл")
        return elapsed_ms, recovery_ms

    def _stop_silero_bridge(self):
        bridge = self.silero_bridge
        self.silero_bridge = None
        if bridge and bridge.poll() is None:
            try:
                bridge.kill()
                bridge.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                pass

    @staticmethod
    def _trim_trailing_silence(path, keep_ms=140, threshold=160):
        """Remove only artificial PCM16 silence appended for short RVC clips."""
        path = Path(path)
        try:
            with wave.open(str(path), "rb") as source:
                params = source.getparams()
                if params.sampwidth != 2 or params.nframes <= 0:
                    return
                frames = source.readframes(params.nframes)
            samples = array("h")
            samples.frombytes(frames)
            channels = max(1, params.nchannels)
            last_active_frame = -1
            for frame_index in range(params.nframes - 1, -1, -1):
                offset = frame_index * channels
                if any(
                    abs(samples[offset + channel]) >= threshold
                    for channel in range(channels)
                ):
                    last_active_frame = frame_index
                    break
            if last_active_frame < 0:
                return
            keep_frames = int(params.framerate * max(0, keep_ms) / 1000.0)
            target_frames = min(params.nframes, last_active_frame + keep_frames + 1)
            if target_frames >= params.nframes - int(params.framerate * 0.15):
                return
            trimmed = samples[:target_frames * channels].tobytes()
            temporary = path.with_suffix(".trim.wav")
            with wave.open(str(temporary), "wb") as output:
                output.setparams(params)
                output.setnframes(target_frames)
                output.writeframes(trimmed)
            temporary.replace(path)
        except (OSError, EOFError, wave.Error, ValueError):
            return

    def _start_rvc(self):
        bridge = self.rvc_root / "jarvis_bridge.py"
        required = (self.rvc_python, bridge, self.rvc_model, self.rvc_index)
        if not self.rvc_enabled or not all(path.exists() for path in required):
            self.rvc_enabled = False
            print("[TTS] RVC-голос JARVIS недоступен, используется Piper.")
            return
        environment = os.environ.copy()
        environment.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        self.rvc_bridge = subprocess.Popen(
            [str(self.rvc_python), str(bridge), str(self.rvc_model), str(self.rvc_index), str(self.rvc_cpu_threads), self.rvc_device],
            cwd=str(self.rvc_root), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8", bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), env=environment,
        )
        print(f"[TTS] Загружается голос JARVIS: {self.rvc_model.name}")
        ready = self._read_rvc_reply(max(60.0, self.rvc_timeout))
        if not ready or ready.get("status") != "ready":
            self._stop_rvc_bridge()
            raise RuntimeError("RVC-мост не подтвердил готовность голосовой модели")

    def _read_rvc_reply(self, timeout):
        bridge = self.rvc_bridge
        if not bridge or not bridge.stdout:
            return None
        replies = queue.Queue(maxsize=1)

        def read_reply():
            try:
                for line in bridge.stdout:
                    if line.startswith("JARVIS_RVC:"):
                        replies.put(json.loads(line.removeprefix("JARVIS_RVC:")), block=False)
                        return
                replies.put(None, block=False)
            except Exception:
                try:
                    replies.put(None, block=False)
                except queue.Full:
                    pass

        threading.Thread(target=read_reply, name="RvcReplyReader", daemon=True).start()
        try:
            return replies.get(timeout=max(3.0, timeout))
        except queue.Empty:
            return None

    def _convert_rvc(self, source, output):
        started = time.perf_counter()
        bridge_recovery_ms = 0.0
        request_ms = 0.0
        try:
            if not self.rvc_enabled:
                return False
            if not self.rvc_bridge or self.rvc_bridge.poll() is not None:
                recovery_started = time.perf_counter()
                self._stop_rvc_bridge()
                try:
                    self._start_rvc()
                except Exception as exc:
                    print(f"[TTS RVC ERROR] Голосовая модель не восстановилась: {exc}")
                    return False
                finally:
                    bridge_recovery_ms += (time.perf_counter() - recovery_started) * 1000.0
            request = {"input": str(source), "output": str(output), "speaker": 0,
                       "pitch": 0, "index_rate": self.rvc_index_rate,
                       "protect": self.rvc_protect, "filter_radius": self.rvc_filter_radius,
                       "method": self.rvc_f0_method}
            try:
                request_started = time.perf_counter()
                self.rvc_bridge.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
                self.rvc_bridge.stdin.flush()
                answer = self._read_rvc_reply(self.rvc_timeout)
                request_ms = (time.perf_counter() - request_started) * 1000.0
                if answer is None:
                    print(f"[TTS RVC ERROR] Голосовая модель не ответила за {self.rvc_timeout:.1f} с; RVC отключён до перезапуска, используется Piper.")
                    self._stop_rvc_bridge()
                    self.rvc_enabled = False
                    return False
                if answer.get("output"):
                    return output.is_file() and output.stat().st_size > 0
                if answer.get("status") == "error":
                    print(f"[TTS RVC ERROR] {answer.get('error')}")
                    return False
            except (BrokenPipeError, OSError, ValueError) as exc:
                print(f"[TTS RVC ERROR] {exc}")
            return False
        finally:
            self.last_rvc_metrics = {
                "rvc_infer_ms": round(request_ms),
                "rvc_recovery_ms": round(bridge_recovery_ms),
                "rvc_total_ms": round((time.perf_counter() - started) * 1000.0),
            }

    def _stop_rvc_bridge(self):
        bridge = self.rvc_bridge
        self.rvc_bridge = None
        if bridge and bridge.poll() is None:
            try:
                bridge.kill()
                bridge.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                pass

    def _worker(self):
        while True:
            text = self.queue.get()

            if text is None:
                return

            text = str(text or "").strip()

            if not text:
                continue

            try:
                self._speak(text)

            except Exception as exc:
                print(f"[TTS ERROR] {exc}")

    def _speak(self, text):
        with tempfile.NamedTemporaryFile(
            suffix=".wav",
            delete=False,
        ) as tmp:
            wav_path = Path(tmp.name)

        try:
            self.render_to_file(text, wav_path)
            self._play_wav(wav_path)
        finally:
            try:
                wav_path.unlink(missing_ok=True)
            except OSError:
                pass

    def render_to_file(self, text, output_path):
        """Создать WAV тем же голосовым конвейером, не воспроизводя его."""
        if not self.enabled:
            raise RuntimeError("Озвучка отключена или не настроена")

        total_started = time.perf_counter()
        prepare_started = time.perf_counter()
        speech_text = prepare_for_tts(text)
        prepare_ms = (time.perf_counter() - prepare_started) * 1000.0
        output_path = Path(output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        base_path = output_path.with_name(
            output_path.stem + f"_{self.tts_engine}.wav"
        )

        render_lock_started = time.perf_counter()
        with self._render_lock:
            render_lock_wait_ms = (time.perf_counter() - render_lock_started) * 1000.0
            self.last_render_used_rvc = False
            self.last_render_metrics = {}
            self.last_rvc_metrics = {}
            output_path.unlink(missing_ok=True)
            base_path.unlink(missing_ok=True)
            base_recovery_ms = 0.0
            if self.tts_engine == "silero":
                base_tts_ms, base_recovery_ms = self._render_silero(
                    speech_text,
                    base_path,
                )
            else:
                cmd = [
                    str(self.piper_exe),
                    "--model",
                    str(self.model),
                    "--config",
                    str(self.config_path),
                    "--output_file",
                    str(base_path),
                    "--length_scale",
                    str(self.length_scale),
                    "--noise_scale",
                    str(self.noise_scale),
                    "--noise_w",
                    str(self.noise_w),
                ]

                base_started = time.perf_counter()
                proc = subprocess.run(
                    cmd,
                    input=speech_text,
                    text=True,
                    encoding="utf-8",
                    capture_output=True,
                    creationflags=getattr(
                        subprocess,
                        "CREATE_NO_WINDOW",
                        0,
                    ),
                )
                base_tts_ms = (time.perf_counter() - base_started) * 1000.0

                if proc.returncode != 0:
                    err = (proc.stderr or proc.stdout or "").strip()
                    raise RuntimeError(
                        "Piper завершился с кодом "
                        f"{proc.returncode}: {err}"
                    )

            converted = self._convert_rvc(base_path, output_path)
            rvc_metrics = dict(self.last_rvc_metrics)
            if not converted:
                if self.rvc_required:
                    base_path.unlink(missing_ok=True)
                    raise RuntimeError("RVC не преобразовал фразу; базовый голос не воспроизводится")
                base_path.replace(output_path)
            else:
                self.last_render_used_rvc = True
                base_path.unlink(missing_ok=True)
                if self.tts_engine == "silero":
                    self._trim_trailing_silence(output_path)

            if not output_path.is_file() or output_path.stat().st_size <= 44:
                raise RuntimeError("Озвучка не создала корректный WAV-файл")

            self.last_render_metrics = {
                "tts_prepare_ms": round(prepare_ms),
                "render_lock_wait_ms": round(render_lock_wait_ms),
                "base_tts_engine": self.tts_engine,
                "base_tts_ms": round(base_tts_ms),
                "base_tts_recovery_ms": round(base_recovery_ms),
                # Kept for older log viewers. It now means the selected base
                # TTS duration, not necessarily Piper.
                "piper_ms": round(base_tts_ms),
                **rvc_metrics,
                "tts_total_ms": round((time.perf_counter() - total_started) * 1000.0),
            }
            return output_path

    def _play_wav(self, path):
        import sounddevice as sd
        import soundfile as sf

        data, samplerate = sf.read(
            str(path),
            dtype="float32",
            always_2d=True,
        )

        # Piper обычно создаёт mono WAV.
        #
        # Voicemeeter AUX — многоканальное устройство,
        # но для обычного голоса достаточно stereo.
        if data.shape[1] == 1:
            data = data.repeat(2, axis=1)

        sd.play(
            data,
            samplerate=samplerate,
            device=self.tts_device,
            blocking=True,
        )

    def say(self, text):
        if not self.enabled or not self.thread:
            return

        text = str(text or "").strip()

        if not text:
            return

        self.queue.put(text)

    def stop(self):
        if self.thread:
            try:
                self.queue.put_nowait(None)
            except Exception:
                pass
        self._stop_silero_bridge()
        self._stop_rvc_bridge()

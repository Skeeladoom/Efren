# JARVIS-VOICE-v0.7.8-SHARED-GIGAAM

import json
from assistant_identity import wake_aliases
import queue
from datetime import datetime
import re
import time
from pathlib import Path

import numpy as np

VOICE_CODE_VERSION = "JARVIS-VOICE-v0.7.8-SHARED-GIGAAM"
BASE_DIR = Path(__file__).resolve().parent
JARVIS_LOG_FILE = BASE_DIR / "logs" / "jarvis.log"

try:
    import sounddevice as sd
except ImportError:
    sd = None




class VoiceUnavailable(RuntimeError):
    pass


class VoiceListener:
    def __init__(self, config, wake_words):
        if sd is None:
            raise VoiceUnavailable(
                "Не установлен sounddevice. "
                "В терминал VS Code: python -m pip install sounddevice numpy"
            )

        self.config = config
        self.device = self._resolve_input_device(
            config.get("voice_device_name"),
            config.get("voice_device"),
        )
        self.blocksize = int(config.get("voice_blocksize", 4000))

        configured = [str(w).lower().strip() for w in wake_words if w]
        aliases = configured + [
            "джарвис", "джарви", "жарвис", "жарви",
            "джервис", "джерви", "жервис", "жерви",
            "джавис", "жавис", "джарвес", "жарвес",
            "джарвису", "джарвиса", "джар вис", "жар вис", "jarvis", "jarvi",
        ]
        self.wake_aliases = tuple(dict.fromkeys(aliases))

        self.stt_backend = str(config.get("jarvis_stt_backend", "shared-stt-server"))
        self.uses_local_gigaam = self.stt_backend == "gigaam-local-cpu"
        self.uses_shared_stt = self.stt_backend in {
            "shared-stt-server",
            "shared-whisper-server",  # compatibility with an older config
        }
        if self.uses_shared_stt:
            from friday_voice_worker import GIGAAM_MODEL_PATH as SHARED_STT_MODEL
        self.whisper_model_name = (
            SHARED_STT_MODEL.name
            if self.uses_shared_stt
            else ("GigaAM v3 RNN-T (CPU)" if self.uses_local_gigaam
                  else str(config.get("whisper_model", "base")))
        )
        self.whisper_device = str(config.get("whisper_device", "cpu"))
        self.whisper_compute_type = str(config.get("whisper_compute_type", "int8"))
        self.whisper_language = str(config.get("whisper_language", "ru"))
        self.whisper_beam_size = int(config.get("whisper_beam_size", 1))
        self.silence_seconds = float(config.get("whisper_silence_seconds", 0.65))
        self.max_utterance_seconds = float(config.get("whisper_max_utterance_seconds", 12.0))
        self.min_utterance_seconds = float(config.get("whisper_min_utterance_seconds", 0.25))
        self.energy_threshold = float(config.get("whisper_energy_threshold", 0.012))
        self.wake_free_command_fallback = bool(config.get("wake_free_command_fallback", False))

        print(f"[VOICE VERSION] {VOICE_CODE_VERSION}")
        self.model = None
        if self.uses_shared_stt:
            print(f"[VOICE] Общая модель распознавания: {SHARED_STT_MODEL}")
        elif self.uses_local_gigaam:
            try:
                from gigaam_local import LocalGigaAM
                self.model = LocalGigaAM(BASE_DIR, config)
                print("[VOICE] GigaAM v3 RNN-T: локально, CPU")
            except Exception as exc:
                raise VoiceUnavailable(f"Не удалось загрузить локальную GigaAM: {exc}") from exc
        else:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise VoiceUnavailable("Для backend faster-whisper не установлен faster-whisper.") from exc
            print(
                f"[VOICE] Загружаю faster-whisper: {self.whisper_model_name} "
                f"({self.whisper_device}/{self.whisper_compute_type})"
            )
            try:
                cpu_options = {}
                if "whisper_cpu_threads" in config:
                    cpu_options = {"cpu_threads": max(1, min(8, int(config["whisper_cpu_threads"]))), "num_workers": 1}
                self.model = WhisperModel(
                    self.whisper_model_name,
                    device=self.whisper_device,
                    compute_type=self.whisper_compute_type,
                    **cpu_options,
                )
            except Exception as exc:
                raise VoiceUnavailable(f"Не удалось загрузить faster-whisper: {exc}") from exc

        try:
            info = sd.query_devices(self.device, "input")
        except Exception as exc:
            raise VoiceUnavailable(
                f"Не удалось открыть input-устройство {self.device!r}: {exc}"
            ) from exc

        self.samplerate = int(info["default_samplerate"])
        self.device_name = str(info["name"])
        self.audio_queue = queue.Queue(maxsize=128)

        self.stop_requested = False
        self.sleeping = False
        self.last_fast_command = ""
        self.last_fast_time = 0.0
        self.last_partial = ""

        print(f"[VOICE] Устройство: {self.device_name}")
        print(f"[VOICE] sample rate={self.samplerate} Hz")
        print(f"[VOICE] blocksize={self.blocksize}")
        print("[VOICE] Wake words: " + ", ".join(self.wake_aliases))
        print(f"[VOICE] STT готов: {self.stt_backend}.")

    @staticmethod
    def _resolve_input_device(preferred_name, fallback):
        """Resolve a stable input by name because PortAudio indexes can move."""
        wanted = str(preferred_name or "").strip().casefold()
        if wanted:
            candidates = []
            for index, device in enumerate(sd.query_devices()):
                if int(device.get("max_input_channels", 0)) <= 0:
                    continue
                name = str(device.get("name", ""))
                if wanted in name.casefold():
                    candidates.append((index, name))
            if candidates:
                # Prefer the first normal PortAudio entry; duplicate host-API
                # entries for the same Voicemeeter bus often occur later.
                return candidates[0][0]
        return fallback

    # =========================================================
    # DIAGNOSTIC LOG
    # =========================================================

    @staticmethod
    def _write_log(event_type, **payload):
        """Best-effort JSONL log. Never blocks or breaks voice recognition."""
        try:
            JARVIS_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            event = {
                "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
                "type": str(event_type),
            }
            event.update(payload)
            with JARVIS_LOG_FILE.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        except OSError:
            pass

    # =========================================================
    # NORMALIZATION
    # =========================================================

    @staticmethod
    def _clean(text):
        text = (
            str(text or "")
            .lower()
            .replace("ё", "е")
        )

        text = re.sub(
            r"[,.!?;:—\-]+",
            " ",
            text,
        )

        return " ".join(
            text.split()
        )

    # =========================================================
    # STOP / SLEEP
    # =========================================================

    def request_stop(self):
        self.stop_requested = True

    def sleep(self):
        self.sleeping = True

    def wake(self):
        self.sleeping = False

    # =========================================================
    # AUDIO CALLBACK
    # =========================================================

    def _callback(
        self,
        indata,
        frames,
        time_info,
        status,
    ):
        if status:
            print(
                "[VOICE STATUS] "
                f"{status}"
            )

        try:
            self.audio_queue.put_nowait(
                bytes(indata)
            )

        except queue.Full:
            try:
                self.audio_queue.get_nowait()

            except queue.Empty:
                pass

            try:
                self.audio_queue.put_nowait(
                    bytes(indata)
                )

            except queue.Full:
                pass

    # =========================================================
    # WAKE DETECTION
    # =========================================================

    def _find_wake(
        self,
        text,
    ):
        """
        Wake-word может находиться В ЛЮБОМ МЕСТЕ
        текущей распознанной фразы.

        Примеры:

        "джарвис который час"
        "который час джарвис"
        "который джарвис час"

        Return:
            (wake, command_without_wake)

        Если wake-word отсутствует:
            (None, None)
        """

        text = self._clean(
            text
        )

        if not text:
            return (
                None,
                None,
            )

        for wake in sorted(
            wake_aliases("jarvis", self.wake_aliases),
            key=len,
            reverse=True,
        ):
            pattern = (
                r"(?<!\w)"
                + re.escape(wake)
                + r"(?!\w)"
            )

            match = re.search(
                pattern,
                text,
                flags=re.IGNORECASE,
            )

            if match is None:
                continue

            # Убираем ТОЛЬКО найденный wake-word.
            before = text[
                :match.start()
            ].strip()

            after = text[
                match.end():
            ].strip()

            command = " ".join(
                part
                for part in (
                    before,
                    after,
                )
                if part
            )

            command = self._clean(
                command
            )

            return (
                wake,
                command,
            )

        return (
            None,
            None,
        )

    # =========================================================
    # FAST DISCORD
    # =========================================================

    def _looks_like_fast_command(
        self,
        text,
    ):
        t = self._clean(
            text
        )

        action_words = (
            "кикни",
            "выкинь",
            "выкини",
            "вышвырни",
            "отключи от войса",
            "выкинь из войса",

            "отключи микрофон",
            "выключи микрофон",
            "замуть",
            "замьють",
            "замьютить",
            "замути",
            "мутни",
            "мьютни",

            "включи микрофон",
            "подключи микрофон",
            "размуть",
            "размути",
            "анмут",
            "анмуть",

            "отключи звук",
            "выключи звук",
            "заглуши",
            "оглуши",
            "дефни",

            "включи звук",
            "подключи звук",
            "верни звук",
            "разглуш",
            "андеф",

            "оффни",
            "офни",
            "оффнуть",
            "офнуть",
            "оффнул",
            "офнул",
            "оффани",
            "офани",

            "полный мут",
            "фулл мут",
            "фул мут",

            "выруби полностью",
            "отключи полностью",
            "полностью выруби",
            "полностью отключи",
        )

        if not any(
            phrase in t
            for phrase in action_words
        ):
            return False

        person_words = (
            "антон",
            "антона",
            "антону",
            "антончик",
            "антончика",
            "антончику",
            "тоха",
            "тоху",
            "тохе",

            "денис",
            "денису",
            "ден",
            "дэн",
            "денчик",
            "денчика",
            "денчику",
            "балыч",
            "балычу",
            "балка",
            "балке",
            "асфальтоукладчик",
            "асфальтоукладчика",
            "асфальтоукладчику",

            "сердюк",
            "сердюка",
            "сердюку",
            "дениса",
            "дэна",
            "дэничка",

            "бодя",
            "бодю",
            "боде",
            "богдан",
            "богдана",
            "богдану",
            "чурка",
            "чурку",
            "чурке",
            "мишаня",
            "мишане",

            "дима",
            "диму",
            "диме",
            "димую",
            "дмитрий",
            "дмитрия",
            "дмитрию",
            "куколд",
            "куколда",
            "куколду",
            "кубышкин",
            "кубышкина",
            "кубышкину",
            "кубик",
            "кубика",
            "кубику",
            "пепельница",
            "пепельницу",
            "пепельнице",

            "жека",
            "жеку",
            "жеке",
            "евгений",
            "евгения",
            "евгению",
            "батя димы",
            "батю димы",
            "бате димы",
            "отец димы",
            "отца димы",
            "отцу димы",
            "спущенка",
            "спущенку",
            "спущенке",

            "назар",
            "назара",
            "назару",
            "назрик",
            "назрика",
            "назрику",

            "никита",
            "никиту",
            "никите",
            "никитин",
            "некит",
            "некита",
            "некиту",
            "садовниченко",
            "садовникова",

            "пушка",
            "пушку",
            "пушке",
            "дарина",
            "дарину",
            "дарине",
            "яндекс карты",
            "карта",
            "карты",
            "трасса",

            "ветер",
            "ветра",
            "ветру",
            "илья",
            "илье",
            "илюха",
            "илюху",
            "илюхе",

            "лена",
            "лену",
            "лене",
        
            "егор",
            "егору",
            "егора"
        
        )

        return any(
            target in t
            for target in person_words
        )

    # =========================================================
    # DUPLICATE PROTECTION
    # =========================================================

    def _already_fast_executed(
        self,
        text,
    ):
        now = time.monotonic()

        if not self.last_fast_command:
            return False

        if (
            now
            - self.last_fast_time
            > 4.0
        ):
            return False

        old = self._clean(
            self.last_fast_command
        )

        new = self._clean(
            text
        )

        if not old or not new:
            return False

        return (
            old == new
            or old in new
            or new in old
        )

    def _mark_fast_executed(
        self,
        text,
    ):
        self.last_fast_command = (
            self._clean(
                text
            )
        )

        self.last_fast_time = (
            time.monotonic()
        )

    # =========================================================
    # PARTIAL
    # =========================================================

    def _handle_partial(
        self,
        text,
        on_text,
    ):
        text = self._clean(
            text
        )

        if not text:
            return

        if text == self.last_partial:
            return

        self.last_partial = text

        wake, command = (
            self._find_wake(
                text
            )
        )

        # Нет JARVIS в ЭТОЙ ЖЕ фразе.
        if wake is None:
            return

        self.wake()

        if not command:
            return

        if not (
            self._looks_like_fast_command(
                command
            )
        ):
            return

        if (
            self._already_fast_executed(
                text
            )
        ):
            return

        print(
            f"FAST: {text}"
        )

        self._write_log(
            "fast",
            text=text,
            accepted=True,
            command=command,
        )

        # Передаём исходную полную фразу,
        # чтобы main/router видел реальный STT.
        on_text(
            text
        )

        self._mark_fast_executed(
            text
        )

    # =========================================================
    # FINAL
    # =========================================================

    @staticmethod
    def _looks_like_command(text):
        text = " ".join(str(text or "").lower().split())
        exact = {
            "который час", "сколько времени", "какое время", "время сейчас",
            "открой блокнот", "открой калькулятор", "открой настройки",
            "сделай скриншот", "сними экран", "покажи команды",
        }
        prefixes = (
            "открой ", "запусти ", "включи ", "закрой ", "выключи ",
            "сверни ", "разверни ", "найди ", "покажи ", "скажи ",
            "озвучь ", "повтори ", "громкость ", "поставь громкость ",
            "сделай громкость ", "сделай скрин", "перезапусти ",
        )
        return text in exact or text.startswith(prefixes)

    def _handle_final(
        self,
        text,
        on_text,
        on_wake,
    ):
        text = self._clean(
            text
        )

        if not text:
            self.last_partial = ""
            return

        print(
            f"HEARD: {text}"
        )

        wake, command = (
            self._find_wake(
                text
            )
        )

        self._write_log(
            "heard",
            text=text,
            accepted=(wake is not None),
            wake=wake or "",
            command=command or "",
        )

        if (
            self._already_fast_executed(
                text
            )
        ):
            self.last_partial = ""
            return

        # =====================================================
        # NO JARVIS IN THIS UTTERANCE = IGNORE
        # =====================================================

        if wake is None:
            # GigaAM occasionally recognizes the command perfectly but drops
            # the assistant name at the beginning.  Only pass phrases that
            # clearly look like supported commands; ordinary conversation is
            # still ignored.
            if self.wake_free_command_fallback and self._looks_like_command(text):
                self._write_log("wake_fallback", text=text, accepted=True,
                                command=text, reason="STT omitted wake word")
                on_text(text)
            self.last_partial = ""
            return

        self.wake()

        # =====================================================
        # JUST "JARVIS"
        # =====================================================

        if not command:
            if on_wake is not None:
                on_wake()

            self.last_partial = ""
            return

        # =====================================================
        # JARVIS ANYWHERE + COMMAND
        # =====================================================

        on_text(
            text
        )

        self.last_partial = ""

    # =========================================================
    # FASTER-WHISPER STT
    # =========================================================

    def _transcribe_pcm(self, pcm_bytes):
        if not pcm_bytes:
            return ""

        audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        if audio.size == 0:
            return ""

        # faster-whisper accepts a float32 waveform. Resample to 16 kHz when needed.
        if self.samplerate != 16000:
            old_x = np.arange(audio.size, dtype=np.float64)
            new_size = max(1, int(round(audio.size * 16000.0 / self.samplerate)))
            new_x = np.linspace(0, max(0, audio.size - 1), new_size)
            audio = np.interp(new_x, old_x, audio).astype(np.float32)

        try:
            if self.uses_local_gigaam:
                return self._clean(self.model.transcribe(audio))
            if self.uses_shared_stt:
                from friday_voice_worker import stt_request as shared_stt_request
                pcm_16khz = np.clip(audio * 32768.0, -32768, 32767).astype(np.int16).tobytes()
                return self._clean(shared_stt_request(pcm_16khz, self.config))

            segments, _info = self.model.transcribe(
                audio,
                language=self.whisper_language,
                beam_size=self.whisper_beam_size,
                vad_filter=False,
                condition_on_previous_text=False,
                temperature=0.0,
                without_timestamps=True,
            )
            text = " ".join(segment.text.strip() for segment in segments if segment.text.strip())
            return self._clean(text)
        except Exception as exc:
            print(f"[VOICE STT ERROR] {exc}")
            return ""

    @staticmethod
    def _chunk_rms(data):
        if not data:
            return 0.0
        samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
        if samples.size == 0:
            return 0.0
        samples /= 32768.0
        return float(np.sqrt(np.mean(samples * samples)))

    # =========================================================
    # LISTENER
    # =========================================================

    def listen_forever(self, on_text, on_wake=None):
        print("[VOICE] Открываю аудиопоток...")

        utterance = bytearray()
        speaking = False
        silence_started = None
        utterance_started = None

        try:
            with sd.RawInputStream(
                samplerate=self.samplerate,
                blocksize=self.blocksize,
                device=self.device,
                dtype="int16",
                channels=1,
                callback=self._callback,
            ):
                print("[VOICE] Поток открыт.")
                self._write_log(
                    "listener_started",
                    device=self.device_name,
                    samplerate=self.samplerate,
                    blocksize=self.blocksize,
                    stt=self.stt_backend,
                    model=self.whisper_model_name,
                )
                print("[VOICE] JARVIS в режиме ожидания.")
                print(
                    "[VOICE] Команда принимается, если слово «Джарвис» "
                    "есть в этой же фразе.\n"
                )

                while not self.stop_requested:
                    try:
                        data = self.audio_queue.get(timeout=0.25)
                    except queue.Empty:
                        continue

                    if self.stop_requested:
                        break

                    now = time.monotonic()
                    rms = self._chunk_rms(data)
                    is_voice = rms >= self.energy_threshold

                    if is_voice:
                        if not speaking:
                            speaking = True
                            utterance_started = now
                            utterance.clear()
                        utterance.extend(data)
                        silence_started = None
                    elif speaking:
                        utterance.extend(data)
                        if silence_started is None:
                            silence_started = now

                    if not speaking:
                        continue

                    elapsed = now - (utterance_started or now)
                    silence_elapsed = (
                        now - silence_started if silence_started is not None else 0.0
                    )

                    should_finish = (
                        silence_started is not None
                        and silence_elapsed >= self.silence_seconds
                    )
                    should_force = elapsed >= self.max_utterance_seconds

                    if not (should_finish or should_force):
                        continue

                    pcm = bytes(utterance)
                    speaking = False
                    utterance.clear()
                    silence_started = None
                    utterance_started = None
                    self.last_partial = ""

                    duration = len(pcm) / (2.0 * float(self.samplerate))
                    if duration < self.min_utterance_seconds:
                        continue

                    text = self._transcribe_pcm(pcm)
                    if text:
                        self._handle_final(text, on_text, on_wake)

        except KeyboardInterrupt:
            raise
        except Exception as exc:
            raise VoiceUnavailable(f"Ошибка аудиопотока: {exc}") from exc
        finally:
            self._write_log("listener_stopped")
            print("[VOICE] Listener остановлен.")

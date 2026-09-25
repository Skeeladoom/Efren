"""Persistent Discord voice STT worker for Friday."""

# JARVIS-FRIDAY-WORKER-v0.1.78-TTS-PHASE-TIMINGS

import atexit
import base64
import ctypes
import hashlib
import io
import json
from assistant_identity import custom_wake, wake_aliases
import math
import os
import queue
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
import wave
from collections import deque
from pathlib import Path

if "--gigaam-server" not in sys.argv:
    from discord_tools import (
        execute_discord_parsed_command,
        execute_discord_voice_command,
        execute_protected_insult,
        ALIASES,
        normalize_discord_speech,
        parse_discord_voice_command,
        resolve_people,
        voice_members,
    )
    from tts import LocalTTS


VERSION = "JARVIS-FRIDAY-WORKER-v0.1.83-PERSISTENT-AUTOMATION"

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.json"
SETTINGS_FILE = BASE_DIR / "jarvis_settings.json"
RECOGNITION_ALIASES_FILE = BASE_DIR / "friday_recognition_aliases.json"
STT_DIAGNOSTIC_LOG = BASE_DIR / "logs" / "gigaam-server.log"
STT_MISS_DIR = BASE_DIR / "runtime" / "friday_stt_misses"
STT_MISS_KEEP_COUNT = 40
STT_INPUT_DIR = BASE_DIR / "runtime" / "friday_stt_inputs"
STT_INPUT_KEEP_COUNT = 60
SCHEDULED_COMMANDS_FILE = BASE_DIR / "runtime" / "friday_scheduled_commands.json"

GIGAAM_PYTHON = Path(r"F:\Efrun\gigaam_env\Scripts\python.exe")
GIGAAM_REPO = Path(r"F:\Efrun\GigaAM")
GIGAAM_MODEL_DIR = Path(r"F:\Efrun\models\gigaam")
GIGAAM_MODEL_PATH = GIGAAM_MODEL_DIR / "v3_rnnt.ckpt"
GIGAAM_MODEL_NAME = "v3_rnnt"

STT_HOST = "127.0.0.1"
STT_PORT = 8766
STT_URL = f"http://{STT_HOST}:{STT_PORT}/transcribe"

SERVER_START_TIMEOUT = 75.0
SERVER_REQUEST_TIMEOUT = 30.0

SAMPLE_RATE = 16000
SAMPLE_WIDTH = 2
CHANNELS = 1

# The dedicated GigaAM server uses Silero VAD. Keep only a near-zero
# corrupt/silent-frame guard here; quiet Discord speech must still reach STT.
DEFAULT_MIN_RMS = 0.00001
# Half a second still rejects clicks while preserving very quickly spoken
# commands that Discord has already isolated as a speaking segment.
DEFAULT_MIN_AUDIO_SECONDS = 0.50
DEFAULT_MAX_AUDIO_SECONDS = 24.0

DEFAULT_PCM_DEDUP_SECONDS = 90.0
DEFAULT_COMMAND_DEDUP_SECONDS = 20.0
DEFAULT_SPEECH_MAX_AGE_SECONDS = 4.0
FOLLOWUP_WINDOW_SECONDS = 12.0
COMMAND_CONFLICT_SECONDS = 3.0
GLOBAL_DUPLICATE_SECONDS = 2.5

CAPTION_HALLUCINATION_RE = re.compile(
    r"(?:редактор(?:ы|ом)?\s+субтитров|"
    r"субтитры\s+(?:сделал|делал|создал|подготовил)|"
    r"(?:семкин|съемкин|сёмкин)\s+корректор|"
    r"корректор\s+(?:егорова|титров|субтитров)|"
    r"спасибо\s+за\s+просмотр|"
    r"продолжение\s+следует|amara\s*\.?\s*org)",
    re.IGNORECASE,
)

WATCHDOG_INTERVAL = 2.0
WATCHDOG_FAILURES_BEFORE_RESTART = 3

# Диагностику одного типа не чаще раза в N секунд.
DIAG_THROTTLE_SECONDS = 2.0

FRIDAY_WAKE_RE = re.compile(
    r"(?:^|\s)"
    r"(?:пятница|пятницу|пятнице|пятниц[а-я]*|пятницаа)"
    r"(?:\s|$|[,.!?])",
    re.IGNORECASE,
)

# A conservative fallback for the recurring small-model truncation
# "пятница" -> "пятни".  Command words and a known target are still required
# later, so ordinary Discord speech cannot execute an action from this alone.
FRIDAY_WAKE_FUZZY_RE = re.compile(
    r"(?:^|\s)(?:пятни|пятничка|пятнадцать|пять[-\s]+надцать|пять[-\s]+нацать|пятьнадцать)(?:\s|$|[,.!?])",
    re.IGNORECASE,
)

FRIDAY_WAKE_WORDS = (
    "пятница",
    "пятницу",
    "пятнице",
    "пятничка",
    # Recurring vowel/consonant shifts produced by Russian Discord speech.
    "пятенса",
    "пятенца",
    "пятинца",
    "пятнеца",
    "пятнадцать",
    "пятьнадцать",
    "пять нацать",
    "пять надцать",
)

# These nominative forms address Friday.  Accusative/dative forms such as
# «Пятницу» and «Пятнице» are intentionally absent because they can be a real
# protected target: «выключи микрофон Пятнице».
FRIDAY_ADDRESS_WORDS = frozenset((
    "пятница",
    "пятницаа",
    "пятничка",
    "пятни",
    "пятенса",
    "пятенца",
    "пятинца",
    "пятнеца",
    "пятнадцать",
    "пятьнадцать",
    "пять нацать",
    "пять надцать",
))

COMMAND_WORDS = (
    "каких не",
    "таких не",
    "за мой",
    "за муд",
    "задеф",
    "задэф",
    "дефни",
    "дэфни",
    "за муть",
    "за мути",
    "за мут",
    "мут ни",
    "мьют ни",
    "раз мьют",
    "за дэф",
    "за деф",
    "деф ни",
    "дэф ни",
    "раз глуш",
    # Bounded Whisper variants of «кикни».  A known Discord target is still
    # required later, so these aliases cannot execute a command on their own.
    "кейкни",
    "кекни",
    "кигни",
    "кихни",
    "кижне",
    "кижни",
    "кикне",
    "кикни",
    "кикну",
    "кикню",
    "кикны",
    "кик",
    "кик ни",
    "кик не",
    "кик ну",
    "кик ню",
    "выкин",
    "выброс",
    "замьют",
    "замьють",
    "мьют",
    "мут",
    "размут",
    "раз мут",
    "раз муть",
    "раз мути",
    "полностью",
    "офф",
    "офни",
    "отключ",
    "включ",
    "микрофон",
    "звук",
    "выключи",
    "отключи",
    "подключи",
    "верни",
    "заглуши",
    "разглуши",
    "выкинь",
)

_stt_process = None
_owns_stt_process = False

_stop_event = threading.Event()
_server_lock = threading.RLock()
_restart_lock = threading.Lock()
_stdout_lock = threading.Lock()
_gpu_inference_lock = threading.Lock()
_tts_priority_event = threading.Event()

_pcm_cache = {}
_command_cache = {}
_diag_times = {}
_friday_tts = None
_instance_mutex = None
_last_spoken_result = ""
_last_spoken_lock = threading.Lock()
FRIDAY_SPEECH_DIR = BASE_DIR / "runtime" / "friday_speech"
FRIDAY_SPEECH_CACHE_DIR = BASE_DIR / "runtime" / "friday_speech_cache"
KICK_SOUND_FILE = BASE_DIR / "sounds" / "awp_02.mp3"
_speech_queue = queue.Queue(maxsize=20)
_speech_thread = None
# A Pudge render may hold the shared GPU for several seconds. Keep the decoded
# Discord utterances in RAM during that window instead of dropping rapid
# commands from several speakers. Typical memory cost stays below 10 MB.
class PerUserEventQueue:
    """Small round-robin queue: one noisy speaker cannot bury everybody else."""

    def __init__(self, max_total=48, max_per_user=6):
        self.max_total = int(max_total)
        self.max_per_user = int(max_per_user)
        self._queues = {}
        self._ready = deque()
        self._ready_set = set()
        self._total = 0
        self._closed = False
        self._condition = threading.Condition()

    def put_nowait(self, event):
        with self._condition:
            if event is None:
                self._closed = True
                self._condition.notify_all()
                return
            user_id = str(event.get("user_id") or "без_имени")
            per_user = self._queues.setdefault(user_id, deque())
            if len(per_user) >= self.max_per_user:
                per_user.popleft()
                self._total -= 1
                diag("USER_QUEUE_OLDEST_DROPPED", user_id, force=True)
            if self._total >= self.max_total:
                raise queue.Full
            if event.get("type") == "fast_command":
                per_user.appendleft(event)
            else:
                per_user.append(event)
            self._total += 1
            if user_id not in self._ready_set:
                self._ready.append(user_id)
                self._ready_set.add(user_id)
            self._condition.notify()

    def get(self, timeout=None):
        deadline = None if timeout is None else time.monotonic() + float(timeout)
        with self._condition:
            while not self._ready:
                if self._closed:
                    return None
                if deadline is None:
                    self._condition.wait()
                else:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise queue.Empty
                    self._condition.wait(remaining)
            user_id = self._ready.popleft()
            self._ready_set.discard(user_id)
            per_user = self._queues[user_id]
            event = per_user.popleft()
            self._total -= 1
            if per_user:
                self._ready.append(user_id)
                self._ready_set.add(user_id)
            else:
                self._queues.pop(user_id, None)
            return event

    def task_done(self):
        return None

    def get_nowait(self):
        return self.get(timeout=0)

    def drop_oldest(self):
        with self._condition:
            if not self._ready:
                raise queue.Empty
            user_id = self._ready[0]
            per_user = self._queues[user_id]
            per_user.popleft()
            self._total -= 1
            if not per_user:
                self._ready.popleft()
                self._ready_set.discard(user_id)
                self._queues.pop(user_id, None)


_event_queue = PerUserEventQueue(max_total=48, max_per_user=6)
_event_thread = None
_control_event_queue = queue.Queue(maxsize=12)
_control_event_thread = None
_wake_probe_queue = queue.Queue(maxsize=48)
_wake_probe_thread = None
_wake_detector_model = None
_wake_detector_error = ""
_command_history = {}
_command_history_lock = threading.Lock()
_last_heard_text = ""
_recognition_aliases_cache = {"mtime": None, "items": {}}
_component_repair_event = threading.Event()
_tts_init_lock = threading.Lock()
_tts_failures = 0
_conversation_context = {}
_conversation_context_lock = threading.Lock()
_recent_actions = {}
_recent_actions_lock = threading.Lock()
_scheduled_commands = []
_scheduled_condition = threading.Condition()
_scheduled_sequence = 0
_permission_cache = {}
_permission_cache_lock = threading.Lock()


def wake_detector_loop(config):
    """CPU wake detector plus a deliberately narrow fast-command path."""
    global _wake_detector_model, _wake_detector_error
    recognizers = {}
    try:
        from vosk import KaldiRecognizer, Model, SetLogLevel

        SetLogLevel(-1)
        model_path = Path(str(config.get("voice_model_path") or ""))
        if not model_path.is_dir():
            raise FileNotFoundError(f"Vosk wake model not found: {model_path}")
        _wake_detector_model = Model(str(model_path))
        send({
            "type": "ready",
            "stage": "wake_detector_ready",
            "backend": "vosk-small-ru",
            "gpu": False,
        })
    except Exception as exc:
        _wake_detector_error = f"{type(exc).__name__}: {exc}"
        send_error("wake_detector_start_failed", _wake_detector_error)

    wake_pattern = re.compile(
        r"(?:^|\s)(?:пятница|пятничка|пятни|пятенса|пятенца|пятинца|пятнеца)(?:\s|$)",
        re.IGNORECASE,
    )

    while not _stop_event.is_set():
        item = _wake_probe_queue.get()
        if item is None:
            return
        try:
            user_id = str(item.get("user_id") or "")
            stream_id = str(item.get("stream_id") or "")
            key = (user_id, stream_id)
            if item.get("type") == "wake_probe_end":
                state = recognizers.pop(key, None)
                if state is not None:
                    fast_stt_started = time.perf_counter()
                    try:
                        result = json.loads(state["recognizer"].FinalResult())
                    except (TypeError, ValueError):
                        result = {}
                    final_text = normalize_text(result.get("text") or state.get("last_text") or "")
                    fast_command = safe_fast_command(final_text)
                    if fast_command:
                        try:
                            _event_queue.put_nowait({
                                "type": "fast_command",
                                "user_id": user_id,
                                "stream_id": stream_id,
                                "text": final_text,
                                "command": fast_command,
                                "fast_stt_ms": round((time.perf_counter() - fast_stt_started) * 1000.0, 1),
                                "audio_started_at_ms": item.get("audio_started_at_ms"),
                                "audio_end_at_ms": item.get("audio_end_at_ms"),
                                "receiver_sent_at_ms": item.get("receiver_sent_at_ms"),
                                "worker_queued_at_ms": item.get("worker_queued_at_ms"),
                                "_worker_received_at_ms": item.get("_worker_received_at_ms"),
                            })
                        except queue.Full:
                            diag("FAST_COMMAND_QUEUE_FULL", user_id, force=True)
                continue
            if _wake_detector_model is None or not user_id or not stream_id:
                continue
            encoded = item.get("pcm")
            if not isinstance(encoded, str):
                continue
            try:
                pcm = base64.b64decode(encoded, validate=True)
            except Exception:
                continue
            if not pcm or len(pcm) % SAMPLE_WIDTH:
                continue

            state = recognizers.get(key)
            if state is None:
                state = {
                    "recognizer": KaldiRecognizer(_wake_detector_model, SAMPLE_RATE),
                    "last_match": "",
                    "hits": 0,
                    "detected": False,
                    "last_text": "",
                    "updated": time.monotonic(),
                }
                recognizers[key] = state
            state["updated"] = time.monotonic()
            recognizer = state["recognizer"]
            is_final = recognizer.AcceptWaveform(pcm)
            raw_result = recognizer.Result() if is_final else recognizer.PartialResult()
            try:
                result = json.loads(raw_result)
            except (TypeError, ValueError):
                result = {}
            candidate = normalize_text(result.get("text") or result.get("partial") or "")
            if candidate:
                state["last_text"] = candidate
            live_wake = custom_wake("friday")
            match = (re.search(r"(?<!\w)" + re.escape(live_wake) + r"(?!\w)", candidate)
                     if live_wake else wake_pattern.search(candidate))
            matched_word = match.group(0).strip() if match else ""
            if matched_word:
                # A Vosk final result already represents a stable utterance
                # boundary (often the natural pause after «Пятница»).
                if is_final:
                    state["hits"] = 2
                elif matched_word == state["last_match"]:
                    state["hits"] += 1
                else:
                    state["last_match"] = matched_word
                    state["hits"] = 1
            elif candidate:
                # Vosk may briefly return an empty partial while revising the
                # same word. Preserve one pending hit across that gap, but
                # reset it as soon as a different non-empty phrase appears.
                state["last_match"] = ""
                state["hits"] = 0

            # Two consecutive partial results protect ordinary conversation
            # from a one-frame Vosk guess without delaying a normal command.
            if state["hits"] >= 2 and not state["detected"]:
                state["detected"] = True
                send({
                    "type": "wake_detected",
                    "user_id": user_id,
                    "stream_id": stream_id,
                    "wake": matched_word,
                    "partial": candidate,
                })

            cutoff = time.monotonic() - 30.0
            stale = [old_key for old_key, value in recognizers.items() if value["updated"] < cutoff]
            for old_key in stale:
                recognizers.pop(old_key, None)
        except Exception as exc:
            send_error("wake_probe_failed", f"{type(exc).__name__}: {exc}")
        finally:
            _wake_probe_queue.task_done()


# =============================================================
# JSON / LOG PIPE
# =============================================================

def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default


def send(payload):
    try:
        line = json.dumps(
            payload,
            ensure_ascii=True,
        ) + "\n"

        with _stdout_lock:
            sys.stdout.write(line)
            sys.stdout.flush()

    except Exception:
        pass


def send_error(code, error, **extra):
    payload = {
        "type": "error",
        "version": VERSION,
        "code": str(code),
        "error": str(error),
    }

    payload.update(extra)
    send(payload)


def diag(stage, user_id="", force=False, **extra):
    """
    Используем type='heard', потому что текущий Friday Log
    уже гарантированно умеет отображать HEARD.

    Это ВРЕМЕННЫЙ диагностический режим.
    """

    key = f"{stage}:{user_id}"

    now = time.monotonic()
    previous = _diag_times.get(key, 0.0)

    if not force:
        if now - previous < DIAG_THROTTLE_SECONDS:
            return

    _diag_times[key] = now

    parts = [f"[DIAG] {stage}"]

    for name, value in extra.items():
        parts.append(f"{name}={value}")

    send(
        {
            "type": "heard",
            "text": " | ".join(parts),
            "accepted": False,
            "reason": "diagnostic",
            "user_id": str(user_id),
        }
    )


# =============================================================
# TEXT
# =============================================================

def normalize_text(text):
    return normalize_discord_speech(text)


def bounded_edit_distance(left, right, limit):
    """Return a Levenshtein distance up to limit, or limit + 1."""
    left = normalize_text(left)
    right = normalize_text(right)
    if abs(len(left) - len(right)) > limit:
        return limit + 1
    previous = list(range(len(right) + 1))
    for row, char_left in enumerate(left, 1):
        current = [row]
        row_min = row
        for column, char_right in enumerate(right, 1):
            value = min(
                current[column - 1] + 1,
                previous[column] + 1,
                previous[column - 1] + (char_left != char_right),
            )
            current.append(value)
            row_min = min(row_min, value)
        if row_min > limit:
            return limit + 1
        previous = current
    return previous[-1]


def fuzzy_word_matches(word, candidates):
    word = normalize_text(word)
    if len(word) < 4:
        return False
    limit = 2 if len(word) >= 7 else 1
    return any(
        bounded_edit_distance(word, candidate, limit) <= limit
        for candidate in candidates
        if " " not in candidate and abs(len(word) - len(candidate)) <= limit
    )


def find_friday_wake(text):
    """Return (start, end, matched_text, mode), accepting bounded STT errors."""
    live_wake = custom_wake("friday")
    if live_wake:
        match = re.search(r"(?<!\w)" + re.escape(live_wake) + r"(?!\w)", text, re.IGNORECASE)
        return (match.start(), match.end(), match.group(0), "exact") if match else None
    for pattern, mode in (
        (FRIDAY_WAKE_RE, "exact"),
        (FRIDAY_WAKE_FUZZY_RE, "alias"),
    ):
        match = pattern.search(text)
        if match:
            return match.start(), match.end(), match.group(0), mode
    for match in re.finditer(r"[a-zа-я]+", text, flags=re.IGNORECASE):
        if fuzzy_word_matches(match.group(0), FRIDAY_WAKE_WORDS):
            return match.start(), match.end(), match.group(0), "edit_distance"
    return None


def command_after_friday_wake(text, wake=None):
    """Return only the command spoken after the first Friday wake phrase."""
    wake = wake or find_friday_wake(text)
    if wake is None:
        return ""

    command = text[wake[1]:]
    while True:
        repeated_wake = find_friday_wake(command)
        if repeated_wake is None:
            break

        wake_word = re.sub(
            r"[^a-zа-я]+",
            " ",
            repeated_wake[2].lower(),
        ).strip()
        if wake_word not in wake_aliases("friday", FRIDAY_ADDRESS_WORDS):
            # «Пятницу/Пятнице» can be the intended command target.
            break

        before = command[:repeated_wake[0]].strip()
        after = command[repeated_wake[1]:].strip()
        parsed_after = parse_discord_voice_command(after) if after else None

        if parsed_after is not None:
            # A fresh command follows the repeated address.  The latest clear
            # command wins instead of mixing actions and names from segments.
            command = after
        else:
            # A stray/trailing repeated address is noise, not a VIP target.
            command = f"{before} {after}".strip()
    return normalize_text(command)


def commands_after_friday_wakes(text, wake=None):
    """Split two explicit «Пятница, ...» commands without mixing targets."""
    wake = wake or find_friday_wake(text)
    if wake is None:
        return []

    remainder = text[wake[1]:]
    commands = []
    while remainder:
        repeated_wake = find_friday_wake(remainder)
        if repeated_wake is None:
            tail = normalize_text(remainder)
            if tail:
                commands.append(tail)
            break

        wake_word = re.sub(
            r"[^a-zа-я]+", " ", repeated_wake[2].lower()
        ).strip()
        if wake_word not in wake_aliases("friday", FRIDAY_ADDRESS_WORDS):
            tail = normalize_text(remainder)
            if tail:
                commands.append(tail)
            break

        before = normalize_text(remainder[:repeated_wake[0]])
        if before:
            commands.append(before)
        remainder = remainder[repeated_wake[1]:]

    return commands


def has_command_word(text):
    # The final Discord parser is the single source of truth for action
    # aliases.  Keeping a second independent gate caused valid variants such
    # as «замудь» to be rejected before they reached discord_tools.py.
    return parse_discord_voice_command(text) is not None


def safe_fast_command(text):
    """Accept only an exact, single-person command from the small CPU model.

    Vosk is used here for speed, not for guessing. Group actions, fuzzy wake
    words, several targets and unknown trailing names always fall back to
    GigaAM.
    """
    normalized = normalize_text(text)
    wake = find_friday_wake(normalized)
    if not wake or normalized[:wake[0]].strip():
        return ""
    wake_word = re.sub(r"[^a-zа-яё]+", " ", wake[2].lower()).strip()
    if wake_word not in wake_aliases("friday", {"пятница", "пятничка"}):
        return ""
    command = command_after_friday_wake(normalized, wake)
    if re.search(r"\b(?:через|секунд\w*|минут\w*|час\w*|потом|затем)\b", command):
        # A timer must never be mistaken for an immediate Vosk fast command.
        return ""
    if not command or re.search(r"(?:,|\bи\b|\bили\b)", command):
        return ""
    parsed = parse_discord_voice_command(command)
    if not parsed:
        return ""
    if parsed.get("action") not in {
        "disconnect", "mute", "unmute", "deaf", "undeaf",
        "full_disable", "full_restore", "off_toggle",
    }:
        return ""
    targets = list(parsed.get("targets") or ())
    target_set = set(targets)
    # Dima has two Discord accounts for one person. Generic «Никита» can mean
    # several different people and therefore must never use the fast path.
    one_person = len(target_set) == 1 or (
        target_set and target_set.issubset({"dima", "dima_alt"})
    )
    if not one_person:
        return ""
    aliases = tuple(
        alias
        for target in targets
        for alias in ALIASES.get(target, ())
    )
    padded = f" {command} "
    if not any(f" {normalize_text(alias)} " in padded for alias in aliases):
        return ""
    return command


def is_repeat_friday_command(text):
    """Whether a post-wake phrase asks to replay Friday's last reply."""
    text = normalize_text(text)
    if not text:
        return False
    return bool(re.search(
        r"(?:\bповтор(?:и|ить|яй)?\b|\bперескажи\b|"
        r"\bскажи\s+(?:ещ[её]\s+раз|снова)\b|"
        r"\b(?:что|ч[её])\s+(?:ты\s+)?сказал[а]?\b)",
        text,
        re.IGNORECASE,
    ))


def get_last_spoken_result():
    with _last_spoken_lock:
        return _last_spoken_result


def load_recognition_aliases():
    """Load user-taught phrase replacements only when the file changes."""
    try:
        stamp = RECOGNITION_ALIASES_FILE.stat().st_mtime_ns
    except OSError:
        stamp = None
    if stamp == _recognition_aliases_cache["mtime"]:
        return _recognition_aliases_cache["items"]
    items = {}
    if stamp is not None:
        try:
            raw = json.loads(RECOGNITION_ALIASES_FILE.read_text(encoding="utf-8"))
            source = raw.get("replacements", raw) if isinstance(raw, dict) else {}
            for wrong, correct in source.items():
                wrong = normalize_text(wrong)
                correct = normalize_text(correct)
                if 2 <= len(wrong) <= 120 and 1 <= len(correct) <= 120 and wrong != correct:
                    items[wrong] = correct
        except (OSError, ValueError, TypeError):
            items = {}
    _recognition_aliases_cache.update(mtime=stamp, items=items)
    return items


def apply_recognition_aliases(text, user_id=""):
    normalized = normalize_text(text)
    for wrong, correct in sorted(load_recognition_aliases().items(), key=lambda item: -len(item[0])):
        pattern = rf"(?<![a-zа-яё0-9]){re.escape(wrong)}(?![a-zа-яё0-9])"
        replaced = re.sub(pattern, correct, normalized, flags=re.IGNORECASE)
        if replaced != normalized:
            diag("RECOGNITION_CORRECTION", user_id, force=True, before=normalized, after=replaced)
            normalized = replaced
    return normalized


REVERSIBLE_ACTIONS = {
    "mute": "unmute", "unmute": "mute",
    "deaf": "undeaf", "undeaf": "deaf",
    "full_disable": "full_restore", "full_restore": "full_disable",
}

NUMBER_WORDS = {
    "одну": 1, "один": 1, "одна": 1, "две": 2, "два": 2,
    "три": 3, "четыре": 4, "пять": 5, "шесть": 6,
    "семь": 7, "восемь": 8, "девять": 9, "десять": 10,
}

ACTION_START_RE = re.compile(
    r"\b(?:кик\w*|выкин\w*|замут\w*|замьют\w*|мут\w*|размут\w*|"
    r"отключ\w*|включ\w*|заглуш\w*|разглуш\w*|офф\w*|верни\w*)\b",
    re.IGNORECASE,
)


def split_compound_commands(command):
    """Split independent actions while preserving several targets of one action."""
    normalized = normalize_text(command)
    if not normalized:
        return []
    pieces = re.split(
        r"\s*(?:;|,\s*(?:а\s+)?|\b(?:потом|затем|а|и)\b)\s*",
        normalized,
        flags=re.IGNORECASE,
    )
    pieces = [piece.strip() for piece in pieces if piece.strip()]
    if len(pieces) <= 1:
        return [normalized]
    # A comma used only for enumeration must not destroy a valid single action.
    parsed_pieces = [parse_discord_voice_command(piece) for piece in pieces]
    if sum(item is not None for item in parsed_pieces) < 2:
        return [normalized]
    merged = []
    for piece, parsed in zip(pieces, parsed_pieces):
        if parsed is not None:
            merged.append(piece)
        elif merged:
            # «замуть Диму и Никиту, а Жеке выключи звук»: the middle
            # target has no repeated action and belongs to the previous part.
            merged[-1] = f"{merged[-1]} {piece}"
        else:
            merged.append(piece)
    return merged


def _active_followup(user_id):
    now = time.monotonic()
    with _conversation_context_lock:
        context = dict(_conversation_context.get(str(user_id)) or {})
        if context and context.get("expires", 0.0) < now:
            _conversation_context.pop(str(user_id), None)
            return {}
    return context


def _remember_followup(user_id, parsed):
    action = str((parsed or {}).get("action") or "")
    if not action or action.startswith("random_") or action in {"genocide", "self_disconnect"}:
        return
    with _conversation_context_lock:
        _conversation_context[str(user_id)] = {
            "action": action,
            "expires": time.monotonic() + FOLLOWUP_WINDOW_SECONDS,
        }


def parse_followup_command(command, user_id):
    parsed = parse_discord_voice_command(command)
    if parsed is not None:
        return parsed
    context = _active_followup(user_id)
    targets = resolve_people(command)
    if not context or not targets:
        return None
    # Deliberately narrow: a follow-up without an action must look like
    # «и Никиту тоже», not arbitrary conversation that happens to name him.
    if not re.search(r"(?:^|\s)(?:и|ещ[её]|также)|\bтоже\b", command, re.IGNORECASE):
        return None
    return {"action": context["action"], "targets": targets, "followup": True}


def parse_command_bundle(command, user_id):
    result = []
    for piece in split_compound_commands(command):
        parsed = parse_followup_command(piece, user_id)
        if parsed is not None:
            result.append((piece, parsed))
    return result


def _actor_permission(user_id):
    if not user_id:
        return "system"
    now = time.monotonic()
    with _permission_cache_lock:
        cached = _permission_cache.get(str(user_id))
        if cached and now - cached[1] <= 2.0:
            return cached[0]
    payload = voice_members()
    for member in payload.get("members", []) if isinstance(payload, dict) else []:
        if str(member.get("id") or "") == str(user_id):
            permission = str(member.get("permission") or "standard")
            break
    else:
        permission = "standard"
    with _permission_cache_lock:
        _permission_cache[str(user_id)] = (permission, now)
    return permission


def _permission_priority(permission):
    return {
        "blocked": 0, "prankster": 1, "standard": 2,
        "trusted": 3, "vip": 4, "system": 5,
    }.get(str(permission), 2)


def _is_vip_actor(user_id):
    return _actor_permission(user_id) == "vip"


def _number_value(raw):
    raw = str(raw or "").lower().strip()
    return int(raw) if raw.isdigit() else NUMBER_WORDS.get(raw)


def _seconds_from_match(value, unit):
    number = _number_value(value)
    if number is None:
        return None
    unit = str(unit or "").lower()
    if unit.startswith(("мин", "минут")):
        number *= 60
    elif unit.startswith(("час", "часов")):
        number *= 3600
    return max(1, min(int(number), 24 * 3600))


def extract_command_timing(command):
    """Return clean command, initial delay and optional automatic restore delay."""
    clean = normalize_text(command)
    delay = 0
    duration = None
    special_delay = re.search(r"\bчерез\s+(секунду|минуту|час)\b", clean, re.IGNORECASE)
    if special_delay:
        delay = {"секунду": 1, "минуту": 60, "час": 3600}[special_delay.group(1).lower()]
        clean = (clean[:special_delay.start()] + " " + clean[special_delay.end():]).strip()
    value_re = r"(\d{1,5}|одну|один|одна|две|два|три|четыре|пять|шесть|семь|восемь|девять|десять)"
    unit_re = r"(секунд\w*|сек\w*|минут\w*|мин\w*|час\w*)"
    delayed = re.search(rf"\bчерез\s+{value_re}\s*{unit_re}\b", clean, re.IGNORECASE)
    if delayed and not delay:
        delay = _seconds_from_match(delayed.group(1), delayed.group(2)) or 0
        clean = (clean[:delayed.start()] + " " + clean[delayed.end():]).strip()
    absolute = re.search(r"\bв\s+([01]?\d|2[0-3])(?:[:.]|\s)([0-5]\d)\b", clean)
    if absolute and not delay:
        now = time.localtime()
        due = time.mktime((now.tm_year, now.tm_mon, now.tm_mday,
                           int(absolute.group(1)), int(absolute.group(2)), 0,
                           now.tm_wday, now.tm_yday, now.tm_isdst))
        if due <= time.time():
            due += 24 * 3600
        delay = max(1, int(due - time.time()))
        clean = (clean[:absolute.start()] + " " + clean[absolute.end():]).strip()
    timed = re.search(rf"\bна\s+{value_re}\s*{unit_re}\b", clean, re.IGNORECASE)
    if timed:
        duration = _seconds_from_match(timed.group(1), timed.group(2))
        clean = (clean[:timed.start()] + " " + clean[timed.end():]).strip()
    special_duration = re.search(r"\bна\s+(секунду|минуту|час)\b", clean, re.IGNORECASE)
    if special_duration and duration is None:
        duration = {"секунду": 1, "минуту": 60, "час": 3600}[special_duration.group(1).lower()]
        clean = (clean[:special_duration.start()] + " " + clean[special_duration.end():]).strip()
    return normalize_text(clean), delay, duration


def _action_signature(parsed):
    return (
        str((parsed or {}).get("action") or ""),
        tuple(sorted(str(item) for item in ((parsed or {}).get("targets") or ()))),
    )


def command_allowed_by_arbiter(parsed, user_id):
    """Collapse cross-speaker spam and keep a higher-role conflict authoritative."""
    action, targets = _action_signature(parsed)
    if not action:
        return False, "empty"
    now = time.monotonic()
    permission = _actor_permission(user_id)
    priority = _permission_priority(permission)
    opposite = {
        "mute": "unmute", "unmute": "mute", "deaf": "undeaf", "undeaf": "deaf",
        "full_disable": "full_restore", "full_restore": "full_disable",
    }
    with _recent_actions_lock:
        for key, value in list(_recent_actions.items()):
            if now - value["time"] > COMMAND_CONFLICT_SECONDS:
                _recent_actions.pop(key, None)
        exact = _recent_actions.get((action, targets))
        if exact and now - exact["time"] <= GLOBAL_DUPLICATE_SECONDS:
            return False, "duplicate"
        reverse = _recent_actions.get((opposite.get(action), targets))
        if reverse and now - reverse["time"] <= COMMAND_CONFLICT_SECONDS:
            if reverse["priority"] > priority:
                return False, "higher_priority_conflict"
        _recent_actions[(action, targets)] = {
            "time": now, "priority": priority, "user_id": str(user_id),
        }
    return True, "accepted"


def _reverse_parsed(parsed):
    reverse = REVERSIBLE_ACTIONS.get(str((parsed or {}).get("action") or ""))
    if not reverse:
        return None
    return {"action": reverse, "targets": list((parsed or {}).get("targets") or ())}


def schedule_parsed_command(parsed, user_id, delay_seconds, label, restore_after=None):
    global _scheduled_sequence
    with _scheduled_condition:
        _scheduled_sequence += 1
        item = {
            "id": _scheduled_sequence,
            "due": time.time() + max(1, int(delay_seconds)),
            "parsed": dict(parsed), "user_id": str(user_id),
            "label": str(label), "restore_after": restore_after,
        }
        _scheduled_commands.append(item)
        _scheduled_commands.sort(key=lambda entry: entry["due"])
        _persist_scheduled_commands_locked()
        _scheduled_condition.notify_all()
    return item


def _persist_scheduled_commands_locked():
    try:
        SCHEDULED_COMMANDS_FILE.parent.mkdir(parents=True, exist_ok=True)
        temporary = SCHEDULED_COMMANDS_FILE.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(_scheduled_commands, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(SCHEDULED_COMMANDS_FILE)
    except OSError as exc:
        send_error("scheduled_commands_save_failed", f"{type(exc).__name__}: {exc}")


def load_scheduled_commands():
    global _scheduled_sequence
    try:
        raw = json.loads(SCHEDULED_COMMANDS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        raw = []
    now = time.time()
    restored = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("parsed"), dict):
            continue
        try:
            due = float(item.get("due"))
            item_id = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        # A task that expired while the computer was off is executed promptly,
        # but ancient forgotten tasks are discarded after one day.
        if due < now - 24 * 3600:
            continue
        item["due"] = max(now + 1.0, due)
        item["id"] = item_id
        restored.append(item)
        _scheduled_sequence = max(_scheduled_sequence, item_id)
    with _scheduled_condition:
        _scheduled_commands[:] = sorted(restored, key=lambda entry: entry["due"])
        _persist_scheduled_commands_locked()
    if restored:
        diag("SCHEDULED_COMMANDS_RESTORED", force=True, count=len(restored))


def cancel_scheduled_commands(user_id):
    if not _is_vip_actor(user_id):
        return "Отменять запланированные команды может только VIP."
    with _scheduled_condition:
        count = len(_scheduled_commands)
        _scheduled_commands.clear()
        _persist_scheduled_commands_locked()
        _scheduled_condition.notify_all()
    return f"Отменила запланированные команды: {count}." if count else "Запланированных команд нет."


def scheduled_command_loop():
    while not _stop_event.is_set():
        with _scheduled_condition:
            while not _scheduled_commands and not _stop_event.is_set():
                _scheduled_condition.wait(1.0)
            if _stop_event.is_set():
                return
            wait_for = _scheduled_commands[0]["due"] - time.time()
            if wait_for > 0:
                _scheduled_condition.wait(min(wait_for, 1.0))
                continue
            item = _scheduled_commands.pop(0)
            _persist_scheduled_commands_locked()
        parsed = item["parsed"]
        allowed, reason = command_allowed_by_arbiter(parsed, item["user_id"])
        if not allowed:
            diag("SCHEDULED_COMMAND_SKIPPED", item["user_id"], force=True,
                 reason=reason, command=item["label"])
            continue
        result = execute_discord_parsed_command(parsed, actor_user_id=item["user_id"])
        send({"type": "command", "user_id": item["user_id"], "text": item["label"],
              "command": item["label"], "ok": result is not None, "result": result,
              "source": "таймер"})
        send_command_feedback(result, item["user_id"], parsed=parsed)
        if item.get("restore_after"):
            reverse = _reverse_parsed(parsed)
            if reverse:
                schedule_parsed_command(reverse, item["user_id"], item["restore_after"],
                                        "автоматическое восстановление")


def prepare_command_entries(command, user_id):
    entries = []
    for piece in split_compound_commands(command):
        clean, delay, duration = extract_command_timing(piece)
        parsed = parse_followup_command(clean, user_id)
        if parsed is not None:
            entries.append({
                "original": piece,
                "command": clean,
                "parsed": parsed,
                "delay": delay,
                "duration": duration,
            })
    return entries


def execute_command_entry(entry, user_id):
    parsed = entry["parsed"]
    delay = int(entry.get("delay") or 0)
    duration = entry.get("duration")
    _remember_followup(user_id, parsed)
    if delay:
        schedule_parsed_command(
            parsed,
            user_id,
            delay,
            entry["original"],
            restore_after=duration,
        )
        return f"Запланировала через {delay} секунд.", True
    allowed, reason = command_allowed_by_arbiter(parsed, user_id)
    if not allowed:
        diag(
            "COMMAND_ARBITER_SKIPPED",
            user_id,
            force=True,
            reason=reason,
            command=entry["original"],
        )
        if reason == "higher_priority_conflict":
            return "Команда отменена более приоритетной командой.", False
        return None, False
    result = execute_discord_parsed_command(parsed, actor_user_id=user_id)
    if duration and result:
        reverse = _reverse_parsed(parsed)
        if reverse:
            schedule_parsed_command(
                reverse,
                user_id,
                duration,
                "автоматическое восстановление",
            )
            result = f"{result} Верну через {duration} секунд."
    return result, True


def remember_command(user_id, command, parsed, result):
    action = str((parsed or {}).get("action") or "")
    targets = list((parsed or {}).get("targets") or ())
    if action not in REVERSIBLE_ACTIONS or not targets or not result:
        return
    lowered = str(result).lower()
    if any(word in lowered for word in ("не удалось", "не понял", "не найден", "нельзя")):
        return
    with _command_history_lock:
        _command_history[str(user_id)] = {
            "action": action, "targets": targets, "command": command,
            "time": time.monotonic(), "undone": False,
        }


def undo_or_correct_command(command, user_id):
    normalized = normalize_text(command)
    is_undo = bool(re.search(r"\b(?:отмени|отменить|верни\s+как\s+было)\b", normalized))
    is_correction = normalized.startswith("не ")
    if not (is_undo or is_correction):
        return None
    with _command_history_lock:
        previous = dict(_command_history.get(str(user_id)) or {})
    if not previous or time.monotonic() - previous.get("time", 0) > 25.0:
        return "Нет недавней обратимой команды для исправления."
    if previous.get("undone"):
        return "Последняя команда уже отменена."
    reverse = REVERSIBLE_ACTIONS.get(previous.get("action"))
    rollback = execute_discord_parsed_command(
        {"action": reverse, "targets": previous["targets"]}, actor_user_id=user_id,
    )
    with _command_history_lock:
        if str(user_id) in _command_history:
            _command_history[str(user_id)]["undone"] = True
    if is_undo and not is_correction:
        return f"Отменила последнюю команду. {rollback}"
    target_phrase = normalized.rsplit(" а ", 1)[-1] if " а " in normalized else normalized
    new_targets = [key for key in resolve_people(target_phrase) if key not in previous["targets"]]
    if not new_targets:
        return f"Предыдущее действие отменила, но новое имя не поняла. {rollback}"
    result = execute_discord_parsed_command(
        {"action": previous["action"], "targets": new_targets}, actor_user_id=user_id,
    )
    remember_command(user_id, command, {"action": previous["action"], "targets": new_targets}, result)
    return f"Исправила. {result}"


def extended_voice_command(command, user_id=""):
    """Small Russian service commands outside the moderation parser."""
    normalized = normalize_text(command)
    if re.search(
        r"\b(?:отмени|отменить|сбрось)\b.{0,40}\b(?:заплан\w*|таймер\w*|отлож\w*)\b",
        normalized,
        re.IGNORECASE,
    ):
        return True, cancel_scheduled_commands(user_id)
    if re.search(
        r"\b(?:что|какие)\b.{0,30}\b(?:заплан\w*|таймер\w*)\b",
        normalized,
        re.IGNORECASE,
    ):
        with _scheduled_condition:
            count = len(_scheduled_commands)
        return True, f"Сейчас запланировано команд: {count}."
    correction = undo_or_correct_command(normalized, user_id)
    if correction is not None:
        return True, correction
    if re.search(r"\b(?:кто|кого)\s+(?:сейчас\s+)?(?:в\s+)?(?:войс(?:е|у|а)?|голосов(?:ом|ой)|канал(?:е|у)?)\b", normalized):
        payload = voice_members()
        members = payload.get("members", []) if isinstance(payload, dict) else []
        names = [str(item.get("displayName") or item.get("username") or "").strip() for item in members]
        names = [name for name in names if name]
        return True, ("Сейчас в голосовом канале: " + ", ".join(names)) if names else "Сейчас голосовой канал пуст."
    if re.search(r"\b(?:проверь\s+себя|диагностик[ау]|состояние\s+систем)\b", normalized):
        stt_ok = stt_health_ok()
        tts_ok = _friday_tts is not None and bool(getattr(_friday_tts, "rvc_enabled", False))
        wake_ok = _wake_detector_model is not None
        return True, (
            "Проверка завершена. Распознавание: " + ("работает" if stt_ok else "ошибка")
            + ", быстрый слух: " + ("работает" if wake_ok else "ошибка")
            + ", голос Пуджа: " + ("работает" if tts_ok else "ошибка") + "."
        )
    if re.search(r"\b(?:что|ч[её])\s+(?:ты\s+)?(?:услышал[ау]?|распознал[ау]?)\b", normalized):
        return True, f"До этой команды я услышала: {_last_heard_text}." if _last_heard_text else "У меня пока нет предыдущей распознанной фразы."
    return False, None


def looks_like_repetition(text):
    text = normalize_text(text)

    if not text:
        return True

    compact = re.sub(r"[^a-zа-яё0-9]", "", text, flags=re.IGNORECASE)

    # Typical ASR failure: one character or a short syllable is emitted many
    # times ("чичичичичи..."), sometimes without spaces.
    if re.search(r"(.)\1{7,}", compact, flags=re.IGNORECASE):
        return True

    if re.search(r"(.{1,6})\1{5,}", compact, flags=re.IGNORECASE):
        return True

    for unit_size in range(1, 7):
        if len(compact) < unit_size * 6:
            continue
        unit = compact[:unit_size]
        if unit and compact == unit * (len(compact) // unit_size):
            return True

    tokens = re.findall(
        r"[a-zа-яё0-9]+",
        text,
        flags=re.IGNORECASE,
    )

    # The same failure can be confined to one long token inside otherwise
    # normal-looking output.
    for token in tokens:
        for unit_size in range(1, min(7, len(token) // 5 + 1)):
            unit = token[:unit_size]
            if len(token) >= unit_size * 6 and token == unit * (len(token) // unit_size):
                return True

    if len(tokens) < 6:
        return False

    counts = {}

    for token in tokens:
        counts[token] = counts.get(token, 0) + 1

    if max(counts.values()) >= 5:
        if max(counts.values()) / len(tokens) >= 0.60:
            return True

    run = 1

    for index in range(1, len(tokens)):
        if tokens[index] == tokens[index - 1]:
            run += 1

            if run >= 5:
                return True
        else:
            run = 1

    return False


def looks_anomalously_long(text, audio_seconds):
    """Reject impossible transcript volume for a short Discord utterance."""
    normalized = normalize_text(text)
    if not normalized:
        return False

    letters = len(re.sub(r"\s+", "", normalized))
    words = len(re.findall(r"[a-zа-яё0-9]+", normalized, flags=re.IGNORECASE))
    seconds = max(0.25, float(audio_seconds or 0.0))

    # Conservative Russian conversational limits. They intentionally leave
    # headroom for fast speakers while rejecting multi-sentence hallucinations
    # returned for one- or two-second Discord packets.
    return (
        letters > max(80, int(seconds * 32.0 + 24.0))
        or words > max(16, int(seconds * 7.0 + 4.0))
    )


def looks_like_caption_hallucination(text):
    """Отсекает характерные выдуманные титры Whisper на зевках и шуме."""
    return bool(CAPTION_HALLUCINATION_RE.search(normalize_text(text)))


# =============================================================
# AUDIO
# =============================================================

def pcm_duration_seconds(pcm):
    if not pcm:
        return 0.0

    return len(pcm) / float(
        SAMPLE_RATE * SAMPLE_WIDTH * CHANNELS
    )


def pcm_rms(pcm):
    if not pcm:
        return 0.0

    usable = len(pcm) - (len(pcm) % 2)

    if usable <= 0:
        return 0.0

    sample_count = usable // 2

    if sample_count <= 0:
        return 0.0

    total = 0.0

    try:
        for (value,) in struct.iter_unpack(
            "<h",
            pcm[:usable],
        ):
            sample = value / 32768.0
            total += sample * sample

    except Exception:
        return 0.0

    return math.sqrt(
        total / sample_count
    )


def pcm_to_wav_bytes(pcm):
    buffer = io.BytesIO()

    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(CHANNELS)
        wav.setsampwidth(SAMPLE_WIDTH)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm)

    return buffer.getvalue()


def save_stt_miss(pcm, user_id, duration, rms):
    """Keep recent ASR misses so they can be judged by listening, not RMS alone."""
    try:
        STT_MISS_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
        milliseconds = int((time.time() % 1.0) * 1000.0)
        safe_user_id = re.sub(r"[^0-9A-Za-z_-]", "_", str(user_id or "unknown"))
        filename = (
            f"{stamp}-{milliseconds:03d}_user-{safe_user_id}_"
            f"{duration:.2f}s_rms-{rms:.6f}.wav"
        )
        output_path = STT_MISS_DIR / filename
        output_path.write_bytes(pcm_to_wav_bytes(pcm))

        recordings = sorted(
            STT_MISS_DIR.glob("*.wav"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for stale_path in recordings[STT_MISS_KEEP_COUNT:]:
            stale_path.unlink(missing_ok=True)

        diag(
            "STT_EMPTY_SAVED",
            user_id,
            force=True,
            file=str(output_path),
        )
    except Exception as exc:
        diag(
            "STT_EMPTY_SAVE_ERROR",
            user_id,
            force=True,
            error=f"{type(exc).__name__}: {exc}",
        )


def save_stt_input(pcm, user_id, duration, rms):
    """Keep a small rolling capture while diagnosing phrases lost before ASR."""
    try:
        STT_INPUT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
        milliseconds = int((time.time() % 1.0) * 1000.0)
        safe_user_id = re.sub(r"[^0-9A-Za-z_-]", "_", str(user_id or "unknown"))
        filename = (
            f"{stamp}-{milliseconds:03d}_user-{safe_user_id}_"
            f"{duration:.2f}s_rms-{rms:.6f}.wav"
        )
        (STT_INPUT_DIR / filename).write_bytes(pcm_to_wav_bytes(pcm))

        recordings = sorted(
            STT_INPUT_DIR.glob("*.wav"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for stale_path in recordings[STT_INPUT_KEEP_COUNT:]:
            stale_path.unlink(missing_ok=True)
    except Exception as exc:
        diag(
            "STT_INPUT_SAVE_ERROR",
            user_id,
            force=True,
            error=f"{type(exc).__name__}: {exc}",
        )


# =============================================================
# DEDUP
# =============================================================

def cleanup_cache(cache, max_age, max_items):
    now = time.monotonic()

    for key, timestamp in list(cache.items()):
        if now - timestamp > max_age:
            cache.pop(key, None)

    if len(cache) <= max_items:
        return

    items = sorted(
        cache.items(),
        key=lambda item: item[1],
    )

    for key, _ in items[:len(cache) - max_items]:
        cache.pop(key, None)


def is_duplicate_pcm(user_id, pcm, config):
    ttl = float(
        config.get(
            "friday_pcm_dedup_seconds",
            DEFAULT_PCM_DEDUP_SECONDS,
        )
    )

    cleanup_cache(
        _pcm_cache,
        ttl,
        512,
    )

    key = (
        str(user_id),
        hashlib.sha1(pcm).hexdigest(),
    )

    now = time.monotonic()
    previous = _pcm_cache.get(key)

    if previous is not None:
        if now - previous <= ttl:
            return True

    _pcm_cache[key] = now
    return False


def is_duplicate_command(user_id, command, config):
    ttl = float(
        config.get(
            "friday_command_dedup_seconds",
            DEFAULT_COMMAND_DEDUP_SECONDS,
        )
    )

    cleanup_cache(
        _command_cache,
        ttl,
        128,
    )

    key = (
        str(user_id),
        normalize_text(command),
    )

    now = time.monotonic()
    previous = _command_cache.get(key)

    if previous is not None:
        if now - previous <= ttl:
            return True

    _command_cache[key] = now
    return False


# =============================================================
# GIGAAM STT SERVER PROCESS
# =============================================================

def port_is_open():
    try:
        with socket.create_connection(
            (STT_HOST, STT_PORT),
            timeout=0.4,
        ):
            return True
    except OSError:
        return False


def stt_health_ok():
    if not port_is_open():
        return False
    try:
        with urllib.request.urlopen(
            f"http://{STT_HOST}:{STT_PORT}/health",
            timeout=1.0,
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return bool(
            payload.get("ready")
            and payload.get("backend") == "gigaam-v3-rnnt"
        )
    except Exception:
        return False


def ensure_files():
    missing = []

    for path in (
        GIGAAM_PYTHON,
        GIGAAM_REPO,
        GIGAAM_MODEL_PATH,
    ):
        if not path.exists():
            missing.append(str(path))

    if missing:
        raise FileNotFoundError(
            "Missing GigaAM files: "
            + " | ".join(missing)
        )


def build_server_command(config):
    vad_threshold = float(
        config.get(
            "friday_stt_vad_threshold",
            config.get("friday_whisper_cpp_vad_threshold", 0.35),
        )
    )

    min_speech_ms = int(
        config.get(
            "friday_stt_min_speech_ms",
            config.get("friday_whisper_cpp_min_speech_ms", 120),
        )
    )

    min_silence_ms = int(
        config.get(
            "friday_stt_min_silence_ms",
            config.get("friday_whisper_cpp_min_silence_ms", 240),
        )
    )

    speech_pad_ms = int(
        config.get(
            "friday_stt_speech_pad_ms",
            config.get("friday_whisper_cpp_speech_pad_ms", 200),
        )
    )

    return [
        str(GIGAAM_PYTHON),
        str(Path(__file__).resolve()),
        "--gigaam-server",
        "--parent-pid",
        str(os.getpid()),
        "--host",
        STT_HOST,
        "--port",
        str(STT_PORT),
        "--model-dir",
        str(GIGAAM_MODEL_DIR),
        "--vad-threshold",
        str(vad_threshold),
        "--min-speech-ms",
        str(min_speech_ms),
        "--min-silence-ms",
        str(min_silence_ms),
        "--speech-pad-ms",
        str(speech_pad_ms),
    ]


def terminate_owned_server():
    global _stt_process
    global _owns_stt_process

    with _server_lock:
        process = _stt_process

        if (
            process is not None
            and _owns_stt_process
        ):
            try:
                if process.poll() is None:
                    if sys.platform == "win32":
                        # A Windows venv launcher starts the real base-Python
                        # interpreter as a child. Terminating only the launcher
                        # leaves GigaAM and its VRAM allocated.
                        subprocess.run(
                            [
                                "taskkill",
                                "/PID",
                                str(process.pid),
                                "/T",
                                "/F",
                            ],
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            timeout=5.0,
                            check=False,
                        )
                    else:
                        process.terminate()

                    try:
                        process.wait(timeout=3.0)
                    except subprocess.TimeoutExpired:
                        process.kill()

            except Exception:
                pass

        _stt_process = None
        _owns_stt_process = False


def start_stt_server(config):
    global _stt_process
    global _owns_stt_process

    ensure_files()

    with _server_lock:
        if port_is_open():
            if stt_health_ok():
                return "existing"
            raise RuntimeError(
                f"Port {STT_PORT} is occupied by an incompatible service"
            )

        terminate_owned_server()

        creationflags = 0

        if sys.platform == "win32":
            creationflags = getattr(
                subprocess,
                "CREATE_NO_WINDOW",
                0,
            )

        STT_DIAGNOSTIC_LOG.parent.mkdir(parents=True, exist_ok=True)
        with STT_DIAGNOSTIC_LOG.open("ab", buffering=0) as diagnostic_log:
            _stt_process = subprocess.Popen(
                build_server_command(config),
                cwd=str(BASE_DIR),
                stdin=subprocess.DEVNULL,
                stdout=diagnostic_log,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
            )

        _owns_stt_process = True

    deadline = (
        time.monotonic()
        + SERVER_START_TIMEOUT
    )

    while time.monotonic() < deadline:
        if stt_health_ok():
            return "started"

        process = _stt_process

        if (
            process is not None
            and process.poll() is not None
        ):
            raise RuntimeError(
                f"GigaAM server exited: {process.returncode}"
            )

        time.sleep(0.10)

    raise TimeoutError(
        "GigaAM server start timeout"
    )


def restart_stt_server(config, reason):
    with _restart_lock:
        # Another recovery path may have restored the port while this caller
        # was waiting for the restart lock.  Do not tear down that fresh server.
        if reason == "watchdog_port_closed" and stt_health_ok():
            diag(
                "STT_SERVER_READY",
                force=True,
                mode="recovered_by_parallel_restart",
            )
            return True

        # Never kill an arbitrary process that merely owns port 8766.  If the
        # server was not spawned by this worker and is wedged, report the exact
        # unrecoverable condition so Node can restart the worker without unsafe
        # process-wide taskkill behavior.
        if port_is_open() and not _owns_stt_process:
            send_error(
                "stt_server_unowned_stalled",
                "Port 8766 is open but the server is not owned by this worker",
                reason=reason,
            )
            return False

        diag(
            "STT_SERVER_RESTARTING",
            force=True,
            reason=reason,
        )
        terminate_owned_server()

        try:
            mode = start_stt_server(config)
        except Exception as exc:
            send_error(
                "stt_restart_failed",
                f"{type(exc).__name__}: {exc}",
            )
            return False

        diag(
            "STT_SERVER_READY",
            force=True,
            mode=mode,
            restored=True,
        )
        return True


# =============================================================
# WATCHDOG
# =============================================================

def watchdog_loop(config):
    previous_alive = True
    consecutive_failures = 0

    while not _stop_event.wait(
        WATCHDOG_INTERVAL
    ):
        try:
            alive = stt_health_ok()

            if alive:
                previous_alive = True
                consecutive_failures = 0
                continue

            consecutive_failures += 1

            # A single short connection failure can happen while the server
            # is accepting/closing an inference request.  Do not drop the
            # recognizer (and incoming speech) unless the failure persists.
            if consecutive_failures < WATCHDOG_FAILURES_BEFORE_RESTART:
                diag(
                    "STT_HEALTH_RETRY",
                    force=True,
                    attempt=consecutive_failures,
                    required=WATCHDOG_FAILURES_BEFORE_RESTART,
                )
                continue

            if previous_alive:
                diag(
                    "STT_SERVER_LOST",
                    force=True,
                    reason="port_8766_closed",
                )

            previous_alive = False

            if restart_stt_server(
                config,
                "watchdog_port_closed",
            ):
                previous_alive = True
                consecutive_failures = 0

        except Exception as exc:
            send_error(
                "watchdog_exception",
                f"{type(exc).__name__}: {exc}",
            )


def perform_stt_request(pcm, config=None, force_full_audio=False):
    request = urllib.request.Request(
        STT_URL,
        data=pcm,
        method="POST",
    )

    request.add_header(
        "Content-Type",
        "application/octet-stream",
    )
    if force_full_audio:
        request.add_header("X-Friday-Full-Audio", "1")

    with urllib.request.urlopen(
        request,
        timeout=SERVER_REQUEST_TIMEOUT,
    ) as response:
        raw = response.read()

    payload = json.loads(
        raw.decode(
            "utf-8",
            errors="replace",
        )
    )

    if isinstance(payload, dict):
        if payload.get("error"):
            raise RuntimeError(
                str(payload["error"])
            )

        return normalize_text(
            payload.get("text", "")
        )

    if isinstance(payload, str):
        return normalize_text(payload)

    return ""


def warm_stt_server():
    """Pay the one-time model/CUDA initialization cost before going ready."""
    sample_count = int(SAMPLE_RATE * 1.20)
    pcm = bytearray(sample_count * SAMPLE_WIDTH)
    for index in range(sample_count):
        envelope = min(1.0, index / 800.0, (sample_count - index) / 800.0)
        frequency = 125.0 + 35.0 * math.sin(index / SAMPLE_RATE * math.tau * 2.1)
        value = int(5200.0 * envelope * math.sin(index / SAMPLE_RATE * math.tau * frequency))
        struct.pack_into("<h", pcm, index * SAMPLE_WIDTH, value)
    started = time.perf_counter()
    try:
        perform_stt_request(bytes(pcm))
        diag(
            "STT_MODEL_WARMED",
            force=True,
            ms=round((time.perf_counter() - started) * 1000.0, 1),
        )
    except Exception as exc:
        send_error("stt_warmup_failed", f"{type(exc).__name__}: {exc}")


def stt_request(pcm, config, force_full_audio=False):
    try:
        return perform_stt_request(pcm, config, force_full_audio=force_full_audio)

    except Exception as exc:
        is_timeout = isinstance(exc, (TimeoutError, socket.timeout))
        if isinstance(exc, urllib.error.URLError):
            is_timeout = is_timeout or isinstance(exc.reason, (TimeoutError, socket.timeout))
        if is_timeout:
            diag(
                "INFERENCE_TIMEOUT",
                force=True,
                timeout=SERVER_REQUEST_TIMEOUT,
            )
        send_error(
            "stt_inference_failed",
            f"{type(exc).__name__}: {exc}",
        )

        restored = restart_stt_server(
            config,
            "inference_failure",
        )

        if not restored:
            raise

        # Одна повторная попытка после восстановления.
        return perform_stt_request(pcm, config, force_full_audio=force_full_audio)


# =============================================================
# TRANSCRIBE
# =============================================================

def transcribe(pcm, config, user_id, force_full_audio=False, save_input=True):
    duration = pcm_duration_seconds(pcm)

    # Temporary rolling diagnostics: unlike the miss-only folder, this also
    # captures successful and too-short inputs so a genuinely missing phrase
    # can be located at the receiver/STT boundary by timestamp.
    if save_input:
        save_stt_input(pcm, user_id, duration, pcm_rms(pcm))

    diag(
        "AUDIO_ANALYZE",
        user_id,
        bytes=len(pcm),
        seconds=round(duration, 3),
    )

    min_duration = float(
        config.get(
            "friday_stt_min_audio_seconds",
            config.get("friday_whisper_min_audio_seconds", DEFAULT_MIN_AUDIO_SECONDS),
        )
    )

    max_duration = float(
        config.get(
            "friday_stt_max_audio_seconds",
            config.get("friday_whisper_max_audio_seconds", DEFAULT_MAX_AUDIO_SECONDS),
        )
    )

    if duration < min_duration:
        diag(
            "DROP_TOO_SHORT",
            user_id,
            seconds=round(duration, 3),
        )
        return "", duration

    if duration > max_duration:
        diag(
            "DROP_TOO_LONG",
            user_id,
            seconds=round(duration, 3),
        )
        return "", duration

    rms = pcm_rms(pcm)

    diag(
        "RMS",
        user_id,
        value=round(rms, 6),
    )

    min_rms = float(
        config.get(
            "friday_stt_min_rms",
            config.get("friday_whisper_min_rms", DEFAULT_MIN_RMS),
        )
    )

    if rms < min_rms:
        diag(
            "DROP_RMS_LOW",
            user_id,
            rms=round(rms, 6),
            threshold=min_rms,
        )
        return "", duration

    diag(
        "STT_START",
        user_id,
        seconds=round(duration, 3),
        force=True,
    )

    started = time.perf_counter()

    # GigaAM and RVC must not use the GTX 1060 simultaneously. Previously an
    # utterance arriving during Pudge rendering was discarded here, so real
    # commands appeared as STT_SKIPPED_DURING_SPEECH. Keep the audio and wait
    # for the shared GPU lock instead: this can delay a command, but can no
    # longer make it disappear.
    if _tts_priority_event.is_set():
        diag("STT_WAITING_FOR_SPEECH_RENDER", user_id, force=True)
    with _gpu_inference_lock:
        text = stt_request(
            pcm,
            config,
            force_full_audio=force_full_audio,
        )

    elapsed_ms = round(
        (
            time.perf_counter()
            - started
        ) * 1000.0,
        1,
    )

    # These checks deliberately happen before any wake-word parsing. ASR noise
    # must never become a command merely because a repeated fragment resembles
    # "Пятница" or an action word.
    if text and looks_like_repetition(text):
        diag(
            "DROP_REPETITION",
            user_id,
            force=True,
            text=text,
        )
        return "", duration

    if text and looks_anomalously_long(text, duration):
        diag(
            "DROP_ASR_TOO_LONG",
            user_id,
            force=True,
            seconds=round(duration, 3),
            text=text,
        )
        return "", duration

    if (
        text
        and not re.search(r"\bпятниц", text, flags=re.IGNORECASE)
        and looks_like_caption_hallucination(text)
    ):
        diag(
            "NO_WAKE",
            user_id,
            force=True,
            text="ложное распознавание зевка или шума отброшено",
            ms=elapsed_ms,
        )
        return "", duration

    diag(
        "STT_RESULT",
        user_id,
        force=True,
        ms=elapsed_ms,
        text=text if text else "<EMPTY>",
    )

    if not text:
        save_stt_miss(pcm, user_id, duration, rms)
        return "", duration

    return text, duration


# =============================================================
# VOICE CONFIRMATIONS
# =============================================================

def init_friday_tts(config):
    if not _tts_init_lock.acquire(blocking=False):
        return False
    try:
        return _init_friday_tts_unlocked(config)
    finally:
        _tts_init_lock.release()


def _init_friday_tts_unlocked(config):
    global _friday_tts
    global _speech_thread

    try:
        FRIDAY_SPEECH_DIR.mkdir(parents=True, exist_ok=True)
        FRIDAY_SPEECH_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        for stale_file in FRIDAY_SPEECH_DIR.glob("friday_*.*"):
            try:
                stale_file.unlink()
            except OSError:
                pass

        voice_config = dict(config)
        voice_config["tts_enabled"] = bool(
            config.get("friday_tts_enabled", config.get("tts_enabled", True))
        )
        voice_config["tts_engine"] = str(
            config.get("friday_tts_engine", config.get("tts_engine", "piper"))
        )
        for key in (
            "silero_tts_python",
            "silero_tts_bridge",
            "silero_tts_model",
            "silero_tts_speaker",
            "silero_tts_sample_rate",
            "silero_tts_threads",
            "silero_tts_timeout_seconds",
        ):
            friday_key = f"friday_{key}"
            if friday_key in config:
                voice_config[key] = config[friday_key]
        voice_config["tts_length_scale"] = float(
            config.get(
                "friday_tts_length_scale",
                config.get("tts_length_scale", 1.0),
            )
        )
        voice_config["tts_noise_scale"] = float(
            config.get(
                "friday_tts_noise_scale",
                config.get("tts_noise_scale", 0.667),
            )
        )
        voice_config["tts_noise_w"] = float(
            config.get(
                "friday_tts_noise_w",
                config.get("tts_noise_w", 0.8),
            )
        )
        voice_config["rvc_enabled"] = bool(
            config.get("friday_rvc_enabled", config.get("rvc_enabled", True))
        )
        voice_config["rvc_model"] = str(
            config.get("friday_rvc_model", config.get("rvc_model", ""))
        )
        voice_config["rvc_index"] = str(
            config.get("friday_rvc_index", config.get("rvc_index", ""))
        )
        voice_config["rvc_required"] = True
        voice_config["rvc_index_rate"] = float(
            config.get(
                "friday_rvc_index_rate",
                config.get("rvc_index_rate", 0.55),
            )
        )
        voice_config["rvc_protect"] = float(
            config.get(
                "friday_rvc_protect",
                config.get("rvc_protect", 0.50),
            )
        )
        voice_config["rvc_filter_radius"] = int(
            config.get(
                "friday_rvc_filter_radius",
                config.get("rvc_filter_radius", 3),
            )
        )
        _friday_tts = LocalTTS(voice_config, playback_enabled=False)
        if not _friday_tts.enabled:
            _friday_tts = None
            diag("FRIDAY_TTS_DISABLED", force=True)
            return False
        if not bool(getattr(_friday_tts, "rvc_enabled", False)):
            _friday_tts.stop()
            _friday_tts = None
            raise RuntimeError("Голос Пуджа недоступен; резервный голос для Пятницы запрещён")

        # Warm RVC before the worker advertises readiness. The Node ready gate
        # discards startup conversation, so the first real command does not
        # pay the expensive Pudge/CUDA initialization cost.
        warmup_path = FRIDAY_SPEECH_DIR / "friday_voice_model_warmup.wav"
        warmup_started = time.perf_counter()
        warmup_error = None
        for attempt in range(1, 3):
            try:
                with _gpu_inference_lock:
                    # Very short Silero clips can leave this older RVC model
                    # waiting indefinitely in pitch extraction. Use a normal
                    # sentence-sized silent warm-up, matching real replies.
                    _friday_tts.render_to_file(
                        "Алё, меня хорошо слышно? Пятница полностью готова к работе.",
                        warmup_path,
                    )
                warmup_error = None
                break
            except RuntimeError as exc:
                warmup_error = exc
                warmup_path.unlink(missing_ok=True)
                diag(
                    "FRIDAY_TTS_WARMUP_RETRY",
                    force=True,
                    attempt=attempt,
                    error=str(exc),
                )
        if warmup_error is not None:
            raise warmup_error
        warmup_path.unlink(missing_ok=True)
        # Anything requested while the heavy voice model was warming up is
        # stale conversation and must never be played after startup.
        while True:
            try:
                _speech_queue.get_nowait()
            except queue.Empty:
                break
        diag(
            "FRIDAY_TTS_READY",
            force=True,
            rvc=bool(getattr(_friday_tts, "rvc_enabled", False)),
            warmup_ms=round((time.perf_counter() - warmup_started) * 1000.0, 1),
        )
        send({
            "type": "ready",
            "version": VERSION,
            "stage": "tts_ready",
            "rvc": bool(getattr(_friday_tts, "rvc_enabled", False)),
        })
        if _speech_thread is None or not _speech_thread.is_alive():
            _speech_thread = threading.Thread(
                target=speech_worker_loop,
                name="FridaySpeechRenderer",
                daemon=True,
            )
            _speech_thread.start()
        return True
    except Exception as exc:
        failed_tts = _friday_tts
        _friday_tts = None
        if failed_tts is not None:
            try:
                failed_tts.stop()
            except Exception:
                pass
        send_error("friday_tts_start_failed", f"{type(exc).__name__}: {exc}")
        return False


def speech_cache_path(text):
    model = _friday_tts.rvc_model if _friday_tts is not None else Path("")
    try:
        model_stamp = f"{model.stat().st_size}:{model.stat().st_mtime_ns}"
    except OSError:
        model_stamp = str(model)
    method = getattr(_friday_tts, "rvc_f0_method", "")
    rvc_enabled = bool(getattr(_friday_tts, "rvc_enabled", False))
    length_scale = getattr(_friday_tts, "length_scale", 1.0)
    noise_scale = getattr(_friday_tts, "noise_scale", 0.667)
    noise_w = getattr(_friday_tts, "noise_w", 0.8)
    index_rate = getattr(_friday_tts, "rvc_index_rate", 0.55)
    protect = getattr(_friday_tts, "rvc_protect", 0.50)
    filter_radius = getattr(_friday_tts, "rvc_filter_radius", 3)
    base_engine = getattr(_friday_tts, "tts_engine", "piper")
    base_model = (
        getattr(_friday_tts, "silero_model", Path(""))
        if base_engine == "silero"
        else getattr(_friday_tts, "model", Path(""))
    )
    try:
        base_model_stamp = f"{base_model.stat().st_size}:{base_model.stat().st_mtime_ns}"
    except OSError:
        base_model_stamp = str(base_model)
    base_speaker = getattr(_friday_tts, "silero_speaker", "")
    digest = hashlib.sha256(
        f"friday-voice-v6|{base_engine}|{base_model_stamp}|{base_speaker}|{rvc_enabled}|{model_stamp}|{method}|{length_scale}|{noise_scale}|{noise_w}|{index_rate}|{protect}|{filter_radius}|{text}".encode("utf-8")
    ).hexdigest()
    return FRIDAY_SPEECH_CACHE_DIR / f"{digest}.wav"


def render_and_send_spoken_result(
    text,
    user_id="",
    queued_at=None,
    max_age=DEFAULT_SPEECH_MAX_AGE_SECONDS,
    feedback_queued_at_ms=None,
    kind="command_feedback",
):
    global _friday_tts, _tts_failures
    text = str(text or "").strip()
    if not text or _friday_tts is None:
        return

    settings = load_json(SETTINGS_FILE, {})
    if not bool(settings.get("tts_enabled", True)):
        return

    speech_path = FRIDAY_SPEECH_DIR / f"friday_{uuid.uuid4().hex}.wav"
    cache_path = speech_cache_path(text)
    cache_hit = cache_path.is_file() and cache_path.stat().st_size > 44
    worker_started = time.perf_counter()
    timings = {
        "speech_queue_wait_ms": round(max(0.0, time.monotonic() - float(queued_at or time.monotonic())) * 1000.0),
        "gpu_wait_ms": 0,
        "cache_io_ms": 0,
    }
    try:
        if cache_hit:
            cache_started = time.perf_counter()
            shutil.copyfile(cache_path, speech_path)
            timings["cache_io_ms"] = round((time.perf_counter() - cache_started) * 1000.0)
        else:
            _tts_priority_event.set()
            try:
                gpu_wait_started = time.perf_counter()
                with _gpu_inference_lock:
                    timings["gpu_wait_ms"] = round((time.perf_counter() - gpu_wait_started) * 1000.0)
                    _friday_tts.render_to_file(text, speech_path)
                    timings.update(dict(getattr(_friday_tts, "last_render_metrics", {}) or {}))
            finally:
                _tts_priority_event.clear()
            if bool(getattr(_friday_tts, "last_render_used_rvc", False)):
                cache_started = time.perf_counter()
                temporary_cache = cache_path.with_suffix(".tmp.wav")
                shutil.copyfile(speech_path, temporary_cache)
                temporary_cache.replace(cache_path)
                timings["cache_io_ms"] = round((time.perf_counter() - cache_started) * 1000.0)
        age_seconds = time.monotonic() - float(queued_at or time.monotonic())
        if age_seconds > max_age:
            speech_path.unlink(missing_ok=True)
            diag(
                "FRIDAY_TTS_STALE_DROPPED",
                str(user_id),
                force=True,
                age=round(age_seconds, 2),
            )
            return
        timings["worker_total_ms"] = round((time.perf_counter() - worker_started) * 1000.0)
        send(
            {
                "type": "speech",
                "kind": str(kind),
                "user_id": str(user_id),
                "text": text,
                "file": str(speech_path),
                "cached": cache_hit,
                "timings": timings,
                "feedback_queued_at_ms": feedback_queued_at_ms,
                "speech_ready_at_ms": time.time() * 1000.0,
            }
        )
        _tts_failures = 0
    except Exception as exc:
        try:
            speech_path.unlink(missing_ok=True)
        except OSError:
            pass
        send_error(
            "friday_tts_render_failed",
            f"{type(exc).__name__}: {exc}",
            user_id=str(user_id),
        )
        _tts_failures += 1
        if _tts_failures >= 3:
            broken_tts = _friday_tts
            _friday_tts = None
            if broken_tts is not None:
                try:
                    broken_tts.stop()
                except Exception:
                    pass
            _component_repair_event.set()


def component_supervisor_loop(config):
    """Repair only the failed Friday component; never restart the whole bot."""
    global _wake_detector_model, _wake_detector_error, _speech_thread
    # Let normal asynchronous startup finish before the first inspection.
    next_tts_attempt = time.monotonic() + 90.0
    next_wake_attempt = time.monotonic() + 10.0
    while not _stop_event.is_set():
        requested = _component_repair_event.wait(10.0)
        _component_repair_event.clear()
        now = time.monotonic()
        if _wake_detector_model is None and (requested or now >= next_wake_attempt):
            next_wake_attempt = now + 30.0
            try:
                from vosk import Model, SetLogLevel
                SetLogLevel(-1)
                model_path = Path(str(config.get("voice_model_path") or ""))
                _wake_detector_model = Model(str(model_path))
                _wake_detector_error = ""
                diag("WAKE_DETECTOR_RESTORED", force=True)
            except Exception as exc:
                _wake_detector_error = f"{type(exc).__name__}: {exc}"
                send_error("wake_detector_repair_failed", _wake_detector_error)
        speech_dead = _speech_thread is not None and not _speech_thread.is_alive()
        if speech_dead and _friday_tts is not None:
            _speech_thread = threading.Thread(
                target=speech_worker_loop, name="FridaySpeechRenderer", daemon=True,
            )
            _speech_thread.start()
            diag("FRIDAY_SPEECH_THREAD_RESTORED", force=True)
        if _friday_tts is None and (requested or now >= next_tts_attempt):
            next_tts_attempt = now + 120.0
            diag("FRIDAY_TTS_REPAIRING", force=True)
            init_friday_tts(config)


def speech_worker_loop():
    while not _stop_event.is_set():
        item = _speech_queue.get()
        if item is None:
            return
        text, user_id, queued_at, max_age, feedback_queued_at_ms, kind = item
        if time.monotonic() - queued_at > max_age:
            diag(
                "FRIDAY_TTS_STALE_DROPPED",
                str(user_id),
                force=True,
                age=round(time.monotonic() - queued_at, 2),
            )
            continue
        render_and_send_spoken_result(
            text, user_id, queued_at, max_age, feedback_queued_at_ms, kind,
        )


def send_spoken_result(
    text,
    user_id="",
    remember=True,
    max_age=DEFAULT_SPEECH_MAX_AGE_SECONDS,
    kind="command_feedback",
):
    global _last_spoken_result
    text = str(text or "").strip()
    if not text:
        return
    if remember:
        with _last_spoken_lock:
            _last_spoken_result = text
    try:
        # A command confirmation supersedes old speech. Manually entered chat
        # text is low priority and must never erase a moderation confirmation.
        if kind != "manual_speech":
            while True:
                try:
                    pending = _speech_queue.get_nowait()
                except queue.Empty:
                    break
                if pending is None:
                    _speech_queue.put_nowait(None)
                    return
        _speech_queue.put_nowait((
            text,
            str(user_id),
            time.monotonic(),
            float(max_age),
            time.time() * 1000.0,
            str(kind),
        ))
    except queue.Full:
        send_error(
            "friday_tts_queue_full",
            "Очередь голосовых ответов Пятницы заполнена",
            user_id=str(user_id),
        )


SUCCESSFUL_KICK_RESULT_RE = re.compile(
    r"^(?:"
    r"кикнул\s+\S|"
    r"случайно\s+кикнул:\s*\S|"
    r"геноцид\s+выполнен\.\s*кикнул:\s*\S"
    r")",
    re.IGNORECASE,
)


def is_successful_kick_result(result):
    """True only when Discord confirms that at least one kick succeeded."""
    return bool(SUCCESSFUL_KICK_RESULT_RE.search(str(result or "").strip()))


_ha_reaction_last_at = None
_ha_reaction_lock = threading.Lock()


def send_ha_reaction(text, user_id=""):
    """One effect per utterance, without wake word or TTS; retain command parsing."""
    global _ha_reaction_last_at
    if not re.search(r"(?<!\w)(?:фитьха|фитька|федьха|витьха|(?:федь|вить)\s+ха|фить)(?!\w)", str(text), re.IGNORECASE):
        return False
    with _ha_reaction_lock:
        now = time.monotonic()
        if _ha_reaction_last_at is not None and now - _ha_reaction_last_at < 2.0:
            return False
        source = BASE_DIR / "sounds" / "Ha!.mp3"
        effect_path = None
        try:
            FRIDAY_SPEECH_DIR.mkdir(parents=True, exist_ok=True)
            effect_path = FRIDAY_SPEECH_DIR / f"friday_ha_{uuid.uuid4().hex}.mp3"
            shutil.copyfile(source, effect_path)
            stamp = time.time() * 1000.0
            send({"type": "speech", "kind": "ha_sound", "user_id": str(user_id),
                  "text": "Звуковая реакция: Ha!", "file": str(effect_path), "cached": True,
                  "feedback_queued_at_ms": stamp, "speech_ready_at_ms": stamp})
            _ha_reaction_last_at = now
            return True
        except Exception as exc:
            if effect_path is not None:
                effect_path.unlink(missing_ok=True)
            send_error("friday_ha_sound_failed", str(exc), user_id=str(user_id))
            return False


def send_kick_sound(result, user_id=""):
    """Send the AWP effect directly to Discord without running Pudge TTS."""
    global _last_spoken_result

    result = str(result or "").strip()
    if result:
        with _last_spoken_lock:
            _last_spoken_result = result

    # A kick supersedes any confirmation that was still waiting for Pudge.
    while True:
        try:
            pending = _speech_queue.get_nowait()
        except queue.Empty:
            break
        if pending is None:
            _speech_queue.put_nowait(None)
            break

    if not KICK_SOUND_FILE.is_file():
        send_error(
            "friday_kick_sound_missing",
            f"Не найден звук кика: {KICK_SOUND_FILE}",
            user_id=str(user_id),
        )
        return False

    try:
        FRIDAY_SPEECH_DIR.mkdir(parents=True, exist_ok=True)
        effect_path = FRIDAY_SPEECH_DIR / f"friday_kick_{uuid.uuid4().hex}.mp3"
        shutil.copyfile(KICK_SOUND_FILE, effect_path)
        send({
            "type": "speech",
            "kind": "kick_sound",
            "user_id": str(user_id),
            "text": result,
            "file": str(effect_path),
            "cached": True,
            "feedback_queued_at_ms": time.time() * 1000.0,
            "speech_ready_at_ms": time.time() * 1000.0,
        })
        return True
    except Exception as exc:
        send_error(
            "friday_kick_sound_failed",
            f"{type(exc).__name__}: {exc}",
            user_id=str(user_id),
        )
        return False


def command_feedback_mode(parsed):
    settings = load_json(SETTINGS_FILE, {})
    modes = settings.get("friday_reply_modes", {})
    action = str((parsed or {}).get("action") or "default")
    default = "sound" if action in {"disconnect", "self_disconnect", "genocide", "random_disconnect"} else "voice"
    mode = str(modes.get(action, modes.get("default", default))).lower()
    return mode if mode in {"voice", "sound", "log", "none"} else default


def send_command_feedback(
    result,
    user_id="",
    max_age=DEFAULT_SPEECH_MAX_AGE_SECONDS,
    parsed=None,
):
    """Apply the configured reply mode; command logging happens separately."""
    mode = command_feedback_mode(parsed)
    if parsed is None and is_successful_kick_result(result):
        mode = "sound"
    if mode in {"log", "none"}:
        return
    if mode == "sound" and is_successful_kick_result(result):
        # Never replace a kick effect with Pudge, even if the sound file is
        # temporarily unavailable: log the fault instead of saying it badly.
        send_kick_sound(result, user_id)
        return
    send_spoken_result(result, user_id, max_age=max_age, kind="command_feedback")


def log_command_timing(event, user_id, source, stt_ms, parse_ms, discord_ms,
                       action_done_at_ms, feedback_queued_at_ms):
    """One readable latency line spanning receiver, ASR and Discord action."""
    audio_start = float(event.get("audio_started_at_ms") or 0)
    audio_end = float(event.get("audio_end_at_ms") or 0)
    receiver_sent = float(event.get("receiver_sent_at_ms") or 0)
    worker_queued = float(event.get("worker_queued_at_ms") or 0)
    worker_received = float(event.get("_worker_received_at_ms") or 0)
    process_started = float(event.get("_process_started_at_ms") or 0)
    diag(
        "COMMAND_TIMING", user_id, force=True, source=source,
        audio_ms=round(max(0.0, audio_end - audio_start), 1) if audio_start and audio_end else "-",
        receiver_ms=round(max(0.0, receiver_sent - audio_end), 1) if audio_end and receiver_sent else "-",
        bridge_ms=round(max(0.0, worker_received - worker_queued), 1) if worker_queued and worker_received else "-",
        queue_ms=round(max(0.0, process_started - worker_received), 1) if worker_received and process_started else "-",
        stt_ms=round(max(0.0, stt_ms), 1), parse_ms=round(max(0.0, parse_ms), 1),
        discord_ms=round(max(0.0, discord_ms), 1),
        end_to_action_ms=round(max(0.0, action_done_at_ms - audio_end), 1) if audio_end else "-",
        end_to_feedback_ms=round(max(0.0, feedback_queued_at_ms - audio_end), 1) if audio_end else "-",
    )


# =============================================================
# EVENT PROCESSING
# =============================================================

def process_event(event, config):
    global _last_heard_text
    event_started = time.perf_counter()
    event["_process_started_at_ms"] = time.time() * 1000.0
    stt_total_ms = float(event.get("fast_stt_ms") or 0.0)

    user_id = str(
        event.get(
            "user_id",
            "",
        )
    )

    diag(
        "STDIN_EVENT",
        user_id,
        keys=",".join(
            sorted(str(k) for k in event.keys())
        ),
    )

    # Text from the local control-panel chat bypasses STT and cannot be
    # interpreted as a Discord moderation command.
    if event.get("type") == "speak":
        speech_text = str(event.get("text") or "").strip()
        if not speech_text:
            diag("DROP_EMPTY_SPEECH", force=True)
            return
        send({
            "type": "speech_request",
            "text": speech_text,
            "source": str(event.get("source") or "local"),
        })
        # Manually entered chat text remains valid while the voice model is
        # warming up or rendering. Command confirmations keep the short limit.
        send_spoken_result(
            speech_text,
            remember=True,
            max_age=120.0,
            kind="manual_speech",
        )
        return

    if event.get("type") == "repair_components":
        _component_repair_event.set()
        send({"type": "component_repair_requested", "source": str(event.get("source") or "local")})
        return

    if event.get("type") == "text_command":
        original_text = str(event.get("text") or "").strip()
        if not original_text:
            diag("DROP_EMPTY_TEXT_COMMAND", user_id, force=True)
            return
        normalized_text = apply_recognition_aliases(original_text, user_id)
        wake = find_friday_wake(normalized_text)
        wake_word = ""
        if wake is not None:
            wake_word = re.sub(r"[^a-zа-я]+", " ", wake[2].lower()).strip()
        # Strip Friday only when it is the leading address. A trailing
        # «Пятнице» may be the protected target of the actual command.
        leading_address = bool(
            wake is not None
            and not normalized_text[:wake[0]].strip()
            and wake_word in wake_aliases("friday", FRIDAY_ADDRESS_WORDS)
        )
        command = (
            command_after_friday_wake(normalized_text, wake)
            if leading_address else
            normalized_text
        )
        handled, result = extended_voice_command(command, user_id)
        entries = [] if handled else prepare_command_entries(command, user_id)
        completed = []
        if handled:
            completed.append((command, None, result, True))
        else:
            for entry in entries:
                entry_result, accepted = execute_command_entry(entry, user_id)
                if entry_result is not None:
                    completed.append((entry["command"], entry["parsed"], entry_result, accepted))
                    if accepted:
                        remember_command(user_id, entry["command"], entry["parsed"], entry_result)
        if not completed:
            # The panel field is both a command line and Friday's speech chat.
            # If the text is not a known moderation command, pronounce it
            # verbatim instead of replacing it with "Команда не распознана".
            send({
                "type": "speech_request",
                "user_id": user_id,
                "text": original_text,
                "source": "control_panel_command_fallback",
            })
            send_spoken_result(
                original_text,
                user_id,
                max_age=120.0,
                kind="manual_speech",
            )
            return
        for completed_command, parsed, result, accepted in completed:
            send({
                "type": "command", "user_id": user_id, "text": original_text,
                "command": completed_command, "ok": bool(accepted),
                "result": result, "source": "control_panel",
            })
        spoken = " ".join(str(item[2]) for item in completed if item[2])
        parsed_items = [item[1] for item in completed if item[1]]
        if any(
            is_successful_kick_result(item[2])
            and command_feedback_mode(item[1]) == "sound"
            for item in completed
        ):
            send_kick_sound(spoken, user_id)
        elif any(command_feedback_mode(item) == "voice" for item in parsed_items) or handled:
            send_spoken_result(spoken, user_id, max_age=120.0)
        return

    if event.get("type") == "fast_command":
        original_text = normalize_text(event.get("text") or "")
        command = safe_fast_command(original_text)
        if not command or command != normalize_text(event.get("command") or ""):
            diag("FAST_COMMAND_REJECTED", user_id, force=True, text=original_text)
            return
        if is_duplicate_command(user_id, command, config):
            diag("COMMAND_DUPLICATE", user_id, force=True, command=command)
            return
        parse_started = time.perf_counter()
        entries = prepare_command_entries(command, user_id)
        entry = entries[0] if len(entries) == 1 else None
        parsed = entry["parsed"] if entry else None
        parse_ms = (time.perf_counter() - parse_started) * 1000.0
        discord_started = time.perf_counter()
        result, accepted = execute_command_entry(entry, user_id) if entry else (None, False)
        discord_ms = (time.perf_counter() - discord_started) * 1000.0
        action_done_at_ms = time.time() * 1000.0
        if result is None or not accepted:
            diag("FAST_COMMAND_REJECTED", user_id, force=True, text=original_text)
            return
        send({
            "type": "fast_command_accepted",
            "user_id": user_id,
            "stream_id": str(event.get("stream_id") or ""),
            "command": command,
        })
        send({
            "type": "command",
            "user_id": user_id,
            "text": original_text,
            "command": command,
            "ok": True,
            "result": result,
            "source": "быстрый_путь",
            "total_ms": round((time.perf_counter() - event_started) * 1000.0, 1),
        })
        remember_command(user_id, command, parsed, result)
        send_command_feedback(result, user_id, parsed=parsed)
        feedback_at_ms = time.time() * 1000.0
        log_command_timing(event, user_id, "быстрый_vosk", stt_total_ms, parse_ms,
                           discord_ms, action_done_at_ms, feedback_at_ms)
        return

    pcm_b64 = event.get(
        "pcm",
        "",
    )

    if not isinstance(pcm_b64, str):
        diag(
            "DROP_PCM_NOT_STRING",
            user_id,
            force=True,
        )
        return

    try:
        pcm = base64.b64decode(
            pcm_b64,
            validate=True,
        )

    except Exception as exc:
        diag(
            "DROP_BAD_BASE64",
            user_id,
            force=True,
            error=str(exc),
        )
        return

    if not pcm:
        diag(
            "DROP_EMPTY_PCM",
            user_id,
        )
        return

    # ---------------------------------------------------------
    # ЭТО ГЛАВНАЯ ТОЧКА:
    # если видим AUDIO_RX — Node реально передал звук.
    # ---------------------------------------------------------

    audio_seconds = pcm_duration_seconds(pcm)

    diag(
        "AUDIO_RX",
        user_id,
        bytes=len(pcm),
        seconds=round(audio_seconds, 3),
    )

    min_audio_seconds = float(
        config.get(
            "friday_stt_min_audio_seconds",
            config.get("friday_whisper_min_audio_seconds", DEFAULT_MIN_AUDIO_SECONDS),
        )
    )

    if audio_seconds < min_audio_seconds:
        diag(
            "DROP_TOO_SHORT_EARLY",
            user_id,
            seconds=round(audio_seconds, 3),
            minimum=round(min_audio_seconds, 3),
        )
        return

    settings = load_json(
        SETTINGS_FILE,
        {},
    )

    friends_voice_enabled = bool(
        settings.get(
            "friends_voice_enabled",
            False,
        )
    )

    friends_can_use_discord = bool(
        settings.get(
            "friends_can_use_discord",
            False,
        )
    )

    if not friends_voice_enabled:
        diag(
            "BLOCK_SETTINGS",
            user_id,
            reason="friends_voice_enabled=false",
            force=True,
        )
        return

    if not friends_can_use_discord:
        diag(
            "BLOCK_SETTINGS",
            user_id,
            reason="friends_can_use_discord=false",
            force=True,
        )
        return

    diag(
        "SETTINGS_OK",
        user_id,
    )

    if is_duplicate_pcm(
        user_id,
        pcm,
        config,
    ):
        diag(
            "DROP_PCM_DUPLICATE",
            user_id,
        )
        return

    diag(
        "PCM_OK",
        user_id,
    )

    try:
        stt_started = time.perf_counter()
        text, audio_seconds = transcribe(
            pcm,
            config,
            user_id,
        )
        stt_total_ms = (time.perf_counter() - stt_started) * 1000.0

    except Exception as exc:
        send_error(
            "transcribe_exception",
            f"{type(exc).__name__}: {exc}",
            user_id=user_id,
        )
        return

    if not text:
        return


    send_ha_reaction(text, user_id)
    text = apply_recognition_aliases(text, user_id)

    insult_result = execute_protected_insult(text, actor_user_id=user_id)
    if insult_result is not None:
        action_done_at_ms = time.time() * 1000.0
        total_ms = round((time.perf_counter() - event_started) * 1000.0, 1)
        send({
            "type": "command",
            "user_id": user_id,
            "text": text,
            "command": "защита от оскорбления",
            "ok": True,
            "result": insult_result,
            "audio_s": round(audio_seconds, 3),
            "total_ms": total_ms,
        })
        send_command_feedback(insult_result, user_id)
        feedback_at_ms = time.time() * 1000.0
        log_command_timing(
            event, user_id, "защита", stt_total_ms, 0.0, 0.0,
            action_done_at_ms, feedback_at_ms,
        )
        return

    wake = find_friday_wake(text)
    followup_context = _active_followup(user_id)
    if not wake and bool(event.get("wake_detected")):
        retry_started = time.perf_counter()
        retry_text, _ = transcribe(
            pcm, config, user_id, force_full_audio=True, save_input=False,
        )
        stt_total_ms += (time.perf_counter() - retry_started) * 1000.0
        retry_text = apply_recognition_aliases(retry_text, user_id)
        if find_friday_wake(retry_text):
            text = retry_text
            wake = find_friday_wake(text)
            diag("STT_SECOND_PASS_USED", user_id, force=True, text=text)
    followup_entries = prepare_command_entries(text, user_id) if followup_context else []
    followup_service = bool(re.search(
        r"\b(?:отмени|отменить|сбрось|кто|кого|проверь|диагностик|что|какие)\b",
        text,
        re.IGNORECASE,
    ))
    valid_followup = any(
        item["parsed"].get("targets")
        or str(item["parsed"].get("action") or "").startswith("random_")
        for item in followup_entries
    ) or followup_service
    if not wake and (not followup_context or not valid_followup):
        diag("NO_WAKE", user_id, force=True, text=text)
        return

    if wake:
        diag(
            "WAKE_FOUND", user_id, force=True, text=text, wake_mode=wake[3],
        )
    else:
        diag(
            "FOLLOWUP_MODE", user_id, force=True, text=text,
            expires_in=round(max(0.0, followup_context["expires"] - time.monotonic()), 1),
        )

    # Only words after the wake phrase belong to the command.  Keeping the
    # preceding conversation made names/actions said moments earlier affect a
    # rapid command.  Also discard accidental repeated leading wake phrases,
    # while preserving «Пятница» when it is a real target after an action.
    commands = commands_after_friday_wakes(text, wake) if wake else [text]

    if not commands:
        diag(
            "WAKE_ONLY",
            user_id,
            force=True,
        )
        return

    repeat_commands = [
        command for command in commands
        if is_repeat_friday_command(command)
    ]
    if repeat_commands:
        repeated_text = get_last_spoken_result()
        result = repeated_text or "Мне пока нечего повторить."
        total_ms = round((time.perf_counter() - event_started) * 1000.0, 1)
        send({
            "type": "command",
            "user_id": user_id,
            "text": text,
            "command": "повтори последнее подтверждение",
            "ok": bool(repeated_text),
            "result": result,
            "audio_s": round(audio_seconds, 3),
            "total_ms": total_ms,
            "repeat": True,
        })
        # This branch intentionally replays speech only: it never repeats the
        # Discord moderation action that originally produced the confirmation.
        send_spoken_result(result, user_id, remember=False)
        return

    previous_heard = _last_heard_text
    _last_heard_text = text

    service_completed = []
    remaining_commands = []
    for command in commands:
        handled, result = extended_voice_command(command, user_id)
        if handled:
            service_completed.append((command, result))
        else:
            remaining_commands.append(command)
    if service_completed:
        # «Что услышала» must report the phrase before the query itself.
        if any(re.search(r"\b(?:услышал|распознал)", item[0]) for item in service_completed):
            _last_heard_text = previous_heard or text
        for command, result in service_completed:
            send({"type": "command", "user_id": user_id, "text": text,
                  "command": command, "ok": True, "result": result,
                  "audio_s": round(audio_seconds, 3)})
        send_spoken_result(" ".join(str(item[1]) for item in service_completed if item[1]), user_id)
        if not remaining_commands:
            return
    commands = remaining_commands

    command_entries = []
    for command in commands:
        command_entries.extend(prepare_command_entries(command, user_id))
    if not command_entries and wake:
        # The normal VAD crop was intelligible enough to hear the wake word but
        # not the action. Retry once with the original full audio. This costs a
        # second GigaAM inference only for a failed command, never continuously.
        retry_started = time.perf_counter()
        retry_text, _ = transcribe(
            pcm, config, user_id, force_full_audio=True, save_input=False,
        )
        stt_total_ms += (time.perf_counter() - retry_started) * 1000.0
        retry_text = apply_recognition_aliases(retry_text, user_id)
        retry_wake = find_friday_wake(retry_text)
        if retry_wake:
            retry_commands = commands_after_friday_wakes(retry_text, retry_wake)
            retry_entries = []
            for retry_command in retry_commands:
                retry_entries.extend(prepare_command_entries(retry_command, user_id))
            if retry_entries:
                text = retry_text
                commands = retry_commands
                command_entries = retry_entries
                diag("STT_SECOND_PASS_USED", user_id, force=True, text=text)
    if not command_entries:
        diag("NO_COMMAND_WORD", user_id, force=True, command=" | ".join(commands))
        return

    completed = []
    parse_total_ms = 0.0
    discord_total_ms = 0.0
    action_done_at_ms = time.time() * 1000.0
    completed_parsed = []
    for entry in command_entries:
        command = entry["command"]
        if is_duplicate_command(user_id, entry["original"], config):
            diag(
                "COMMAND_DUPLICATE",
                user_id,
                force=True,
                command=command,
            )
            continue
        parse_started = time.perf_counter()
        parsed = entry["parsed"]
        parse_total_ms += (time.perf_counter() - parse_started) * 1000.0
        discord_started = time.perf_counter()
        result, accepted = execute_command_entry(entry, user_id)
        discord_total_ms += (time.perf_counter() - discord_started) * 1000.0
        action_done_at_ms = time.time() * 1000.0
        if accepted:
            remember_command(user_id, command, parsed, result)
        if result is not None:
            completed.append((command, result))
            completed_parsed.append(parsed)

    if not completed:
        return

    total_ms = round(
        (
            time.perf_counter()
            - event_started
        ) * 1000.0,
        1,
    )

    for command, result in completed:
        send({
            "type": "command",
            "user_id": user_id,
            "text": text,
            "command": command,
            "ok": result is not None,
            "result": result,
            "audio_s": round(
                audio_seconds,
                3,
            ),
            "total_ms": total_ms,
        })
    spoken_result = " ".join(
        str(result).strip() for _, result in completed if result
    )
    if any(
        is_successful_kick_result(result)
        and command_feedback_mode(parsed) == "sound"
        for (_, result), parsed in zip(completed, completed_parsed)
    ):
        # If several rapid commands were handled together and at least one of
        # them kicked somebody, one clear AWP effect replaces all Pudge speech.
        send_kick_sound(spoken_result, user_id)
    elif any(command_feedback_mode(parsed) == "voice" for parsed in completed_parsed):
        send_spoken_result(spoken_result, user_id)
    feedback_at_ms = time.time() * 1000.0
    log_command_timing(event, user_id, "gigaam", stt_total_ms, parse_total_ms,
                       discord_total_ms, action_done_at_ms, feedback_at_ms)


def event_worker_loop(config):
    while not _stop_event.is_set():
        item = _event_queue.get()
        if item is None:
            return
        try:
            process_event(item, config)
        except Exception as exc:
            send_error("event_processing_error", f"{type(exc).__name__}: {exc}")
        finally:
            _event_queue.task_done()


def control_event_worker_loop(config):
    while not _stop_event.is_set():
        item = _control_event_queue.get()
        if item is None:
            return
        try:
            process_event(item, config)
        except Exception as exc:
            send_error("control_event_processing_error", f"{type(exc).__name__}: {exc}")
        finally:
            _control_event_queue.task_done()


# =============================================================
# SHUTDOWN
# =============================================================

def acquire_single_instance():
    """ОС сама освобождает mutex даже после аварийного завершения процесса."""
    global _instance_mutex
    if sys.platform != "win32":
        return True
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, "Local\\EFREN_FridayVoiceWorker")
    if not handle:
        return False
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        kernel32.CloseHandle(ctypes.c_void_p(handle))
        return False
    _instance_mutex = handle
    return True


def shutdown():
    global _instance_mutex
    _stop_event.set()
    with _scheduled_condition:
        _scheduled_condition.notify_all()
    terminate_owned_server()
    try:
        _speech_queue.put_nowait(None)
    except queue.Full:
        pass
    try:
        _event_queue.put_nowait(None)
    except queue.Full:
        pass
    try:
        _control_event_queue.put_nowait(None)
    except queue.Full:
        pass
    try:
        _wake_probe_queue.put_nowait(None)
    except queue.Full:
        pass
    if _friday_tts is not None:
        try:
            _friday_tts.stop()
        except Exception:
            pass
    if _instance_mutex is not None and sys.platform == "win32":
        try:
            ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(_instance_mutex))
        except Exception:
            pass
        _instance_mutex = None


atexit.register(shutdown)


# =============================================================
# DEDICATED GIGAAM SERVER (runs inside F:\Efrun\gigaam_env)
# =============================================================

def gigaam_server_main():
    """Serve GigaAM in a small persistent process isolated from Friday/RVC."""
    import argparse
    from http.server import BaseHTTPRequestHandler, HTTPServer

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--gigaam-server", action="store_true")
    parser.add_argument("--parent-pid", type=int, default=0)
    parser.add_argument("--host", default=STT_HOST)
    parser.add_argument("--port", type=int, default=STT_PORT)
    parser.add_argument("--model-dir", default=str(GIGAAM_MODEL_DIR))
    parser.add_argument("--vad-threshold", type=float, default=0.35)
    parser.add_argument("--min-speech-ms", type=int, default=120)
    parser.add_argument("--min-silence-ms", type=int, default=240)
    parser.add_argument("--speech-pad-ms", type=int, default=200)
    args = parser.parse_args()

    # Imports stay inside this mode so the main Friday environment and its RVC
    # dependencies remain untouched.
    import torch
    import gigaam
    from silero_vad import get_speech_timestamps, load_silero_vad

    if not torch.cuda.is_available():
        raise RuntimeError("GigaAM: CUDA device is unavailable")

    torch.set_num_threads(1)
    # Discord packets have many different lengths; cuDNN benchmarking would
    # benchmark a new shape and add latency to otherwise short commands.
    torch.backends.cudnn.benchmark = False
    model = gigaam.load_model(
        GIGAAM_MODEL_NAME,
        fp16_encoder=True,
        use_flash=False,
        device="cuda:0",
        download_root=args.model_dir,
    )
    vad_model = load_silero_vad(onnx=False)

    # Warm CUDA kernels before opening the port. Otherwise the first real
    # Discord command pays a one-off delay of roughly two seconds.
    warmup_path = None
    try:
        warmup_pcm = bytearray(int(SAMPLE_RATE * 1.20) * SAMPLE_WIDTH)
        for sample_index in range(len(warmup_pcm) // SAMPLE_WIDTH):
            envelope = min(
                1.0,
                sample_index / 800.0,
                ((len(warmup_pcm) // SAMPLE_WIDTH) - sample_index) / 800.0,
            )
            sample = int(
                5200.0
                * envelope
                * math.sin(sample_index / SAMPLE_RATE * math.tau * 145.0)
            )
            struct.pack_into("<h", warmup_pcm, sample_index * SAMPLE_WIDTH, sample)
        with tempfile.NamedTemporaryFile(
            prefix="friday_gigaam_warmup_",
            suffix=".wav",
            delete=False,
        ) as temporary:
            warmup_path = temporary.name
        with wave.open(warmup_path, "wb") as wav_file:
            wav_file.setnchannels(CHANNELS)
            wav_file.setsampwidth(SAMPLE_WIDTH)
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(warmup_pcm)
        model.transcribe(warmup_path)
        torch.cuda.synchronize()
    finally:
        if warmup_path:
            try:
                Path(warmup_path).unlink()
            except OSError:
                pass

    def transcribe_pcm_bytes(pcm_bytes):
        """Run the model for PCM without duplicating temporary-file handling."""
        pcm_tensor = torch.frombuffer(
            bytearray(pcm_bytes),
            dtype=torch.int16,
        ).float()
        if pcm_tensor.numel():
            normalized = pcm_tensor / 32768.0
            current_rms = float(torch.sqrt(torch.mean(normalized * normalized)).item())
            peak = float(torch.max(torch.abs(normalized)).item())
            if current_rms > 0.0001 and peak > 0.0:
                # GigaAM does not normalize input amplitude itself. Discord's
                # noise suppression can leave perfectly understandable speech
                # at RMS 0.002-0.02, where RNNT sometimes returns EMPTY.
                gain = min(16.0, 0.060 / current_rms, 0.95 / peak)
                if gain > 1.15:
                    pcm_tensor.mul_(gain).clamp_(-32768.0, 32767.0)
                    pcm_bytes = pcm_tensor.to(torch.int16).numpy().tobytes()

        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix="friday_gigaam_",
                suffix=".wav",
                delete=False,
            ) as temporary:
                temporary_path = temporary.name
            with wave.open(temporary_path, "wb") as wav_file:
                wav_file.setnchannels(CHANNELS)
                wav_file.setsampwidth(SAMPLE_WIDTH)
                wav_file.setframerate(SAMPLE_RATE)
                wav_file.writeframes(pcm_bytes)
            result = model.transcribe(temporary_path)
            return str(getattr(result, "text", result) or "").strip()
        finally:
            if temporary_path:
                try:
                    Path(temporary_path).unlink()
                except OSError:
                    pass

    class GigaAMRequestHandler(BaseHTTPRequestHandler):
        server_version = "FridayGigaAM/1.0"

        def log_message(self, format_string, *format_args):
            print(
                "[GigaAM HTTP] " + (format_string % format_args),
                flush=True,
            )

        def send_json(self, status, payload):
            encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self):
            if self.path != "/health":
                self.send_json(404, {"error": "not_found"})
                return
            self.send_json(
                200,
                {
                    "ready": True,
                    "backend": "gigaam-v3-rnnt",
                    "vad": "silero-vad-6.2.1",
                    "cuda_allocated_mb": round(
                        torch.cuda.memory_allocated(0) / 1024.0 / 1024.0,
                        1,
                    ),
                    "cuda_reserved_mb": round(
                        torch.cuda.memory_reserved(0) / 1024.0 / 1024.0,
                        1,
                    ),
                },
            )

        def do_POST(self):
            if self.path != "/transcribe":
                self.send_json(404, {"error": "not_found"})
                return

            try:
                length = int(self.headers.get("Content-Length", "0"))
                maximum = int(SAMPLE_RATE * SAMPLE_WIDTH * 24.5)
                if length <= 0 or length > maximum or length % SAMPLE_WIDTH:
                    self.send_json(400, {"error": "invalid_pcm_length"})
                    return

                pcm = self.rfile.read(length)
                force_full_audio = self.headers.get("X-Friday-Full-Audio", "") == "1"
                audio = torch.frombuffer(
                    bytearray(pcm),
                    dtype=torch.int16,
                ).float().div_(32768.0)
                speech = [] if force_full_audio else get_speech_timestamps(
                    audio,
                    vad_model,
                    threshold=args.vad_threshold,
                    sampling_rate=SAMPLE_RATE,
                    min_speech_duration_ms=args.min_speech_ms,
                    min_silence_duration_ms=args.min_silence_ms,
                    speech_pad_ms=args.speech_pad_ms,
                )
                audio_rms = float(torch.sqrt(torch.mean(audio * audio)).item())
                vad_fallback = False
                if force_full_audio:
                    first_sample = 0
                    last_sample = len(audio)
                    vad_fallback = True
                elif speech:
                    first_sample = max(0, int(speech[0]["start"]))
                    last_sample = min(len(audio), int(speech[-1]["end"]))
                elif len(audio) >= int(SAMPLE_RATE * 0.75) and audio_rms >= 0.001:
                    # Discord noise suppression can make quiet speech look
                    # unlike speech to Silero. Let GigaAM decide instead of
                    # returning EMPTY without ever running ASR.
                    first_sample = 0
                    last_sample = len(audio)
                    vad_fallback = True
                else:
                    self.send_json(
                        200,
                        {
                            "text": "",
                            "speech_seconds": 0.0,
                            "vad_fallback": False,
                        },
                    )
                    return

                speech_pcm = pcm[first_sample * SAMPLE_WIDTH:last_sample * SAMPLE_WIDTH]
                text_result = transcribe_pcm_bytes(speech_pcm)

                # Cropping sometimes removes a quiet wake word. Retry only a
                # genuinely uncertain short result and only when VAD actually
                # cut the recording. Normal speech still costs one inference.
                cropped = first_sample > 0 or last_sample < len(audio)
                short_words = re.findall(r"[a-zа-яё0-9]+", text_result.lower())
                has_friday = bool(re.search(
                    r"\b(?:пятниц\w*|пятничк\w*|пятни|пятен[сц]а|пятинца)\b",
                    text_result,
                    flags=re.IGNORECASE,
                ))
                uncertain = not text_result or (
                    len(audio) <= int(SAMPLE_RATE * 6.0)
                    and len(short_words) <= 4
                    and not has_friday
                )
                retry_used = False
                if cropped and uncertain:
                    retry_text = transcribe_pcm_bytes(pcm)
                    retry_has_friday = bool(re.search(
                        r"\b(?:пятниц\w*|пятничк\w*|пятни|пятен[сц]а|пятинца)\b",
                        retry_text,
                        flags=re.IGNORECASE,
                    ))
                    if retry_text and (not text_result or retry_has_friday):
                        text_result = retry_text
                        first_sample = 0
                        last_sample = len(audio)
                    vad_fallback = True
                    retry_used = True

                self.send_json(
                    200,
                    {
                        "text": text_result,
                        "speech_seconds": round(
                            (last_sample - first_sample) / float(SAMPLE_RATE),
                            3,
                        ),
                        "vad_fallback": vad_fallback,
                        "uncertainty_retry": retry_used,
                        "audio_rms": round(audio_rms, 6),
                    },
                )
            except Exception as exc:
                print(
                    f"[GigaAM ERROR] {type(exc).__name__}: {exc}",
                    flush=True,
                )
                self.send_json(
                    500,
                    {"error": f"{type(exc).__name__}: {exc}"},
                )

    print(
        json.dumps(
            {
                "ready": True,
                "backend": "gigaam-v3-rnnt",
                "model": GIGAAM_MODEL_NAME,
                "vad": "silero-vad-6.2.1",
                "device": torch.cuda.get_device_name(0),
                "fp16_encoder": True,
                "host": args.host,
                "port": args.port,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    server = HTTPServer((args.host, args.port), GigaAMRequestHandler)

    if args.parent_pid > 0 and sys.platform == "win32":
        # Node may terminate the worker abruptly during restart. Tie the STT
        # server to the worker process so an orphan cannot keep the old model
        # and configuration alive on port 8766.
        synchronize_access = 0x00100000
        infinite_wait = 0xFFFFFFFF
        parent_handle = ctypes.windll.kernel32.OpenProcess(
            synchronize_access,
            False,
            args.parent_pid,
        )
        if not parent_handle:
            server.server_close()
            raise RuntimeError(f"Parent worker {args.parent_pid} is unavailable")

        def stop_with_parent():
            try:
                ctypes.windll.kernel32.WaitForSingleObject(
                    parent_handle,
                    infinite_wait,
                )
                server.shutdown()
            finally:
                ctypes.windll.kernel32.CloseHandle(parent_handle)

        threading.Thread(
            target=stop_with_parent,
            name="FridaySttParentWatchdog",
            daemon=True,
        ).start()

    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


# =============================================================
# MAIN
# =============================================================

def main():
    global _event_thread, _control_event_thread, _wake_probe_thread
    # Node writes JSON lines as UTF-8.  On Russian Windows, inherited stdin
    # can otherwise use a legacy code page and corrupt text entered in the
    # control-panel chat before TTS sees it.
    try:
        sys.stdin.reconfigure(encoding="utf-8", errors="strict")
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    if not acquire_single_instance():
        send(
            {
                "type": "fatal",
                "version": VERSION,
                "error": "friday_worker_already_running",
            }
        )
        return 3

    config = load_json(
        CONFIG_FILE,
        {},
    )

    send(
        {
            "type": "ready",
            "version": VERSION,
            "stage": "worker_started",
        }
    )

    try:
        server_mode = start_stt_server(
            config
        )

    except Exception as exc:
        send(
            {
                "type": "fatal",
                "version": VERSION,
                "error": (
                    "stt_server_start_failed: "
                    f"{type(exc).__name__}: {exc}"
                ),
            }
        )
        return 2

    warm_stt_server()

    send(
        {
            "type": "ready",
            "version": VERSION,
            # Node uses this stable stage name for compatibility. The backend
            # field below identifies the actual recognizer.
            "stage": "whisper_ready",
            "backend": "gigaam-v3-rnnt",
            "server": (
                f"{STT_HOST}:{STT_PORT}"
            ),
            "server_mode": server_mode,
            "gpu": True,
            "gpu_device": 0,
            "diagnostic": True,
        }
    )

    diag(
        "STT_SERVER_READY",
        force=True,
        mode=server_mode,
        server=f"{STT_HOST}:{STT_PORT}",
        backend="gigaam-v3-rnnt",
    )

    watchdog = threading.Thread(
        target=watchdog_loop,
        args=(config,),
        name="FridaySttWatchdog",
        daemon=True,
    )

    watchdog.start()

    _event_thread = threading.Thread(
        target=event_worker_loop,
        args=(config,),
        name="FridayEventProcessor",
        daemon=True,
    )
    _event_thread.start()

    _control_event_thread = threading.Thread(
        target=control_event_worker_loop,
        args=(config,),
        name="FridayControlEventProcessor",
        daemon=True,
    )
    _control_event_thread.start()

    _wake_probe_thread = threading.Thread(
        target=wake_detector_loop,
        args=(config,),
        name="FridayWakeDetector",
        daemon=True,
    )
    _wake_probe_thread.start()

    load_scheduled_commands()
    threading.Thread(
        target=scheduled_command_loop,
        name="FridayScheduledCommands",
        daemon=True,
    ).start()

    # RVC/Pudge прогревается заметно дольше Whisper. Распознавание не должно
    # молчать всё это время: подтверждения голоса просто подключатся, когда
    # фоновая подготовка завершится.
    threading.Thread(
        target=init_friday_tts,
        args=(config,),
        name="FridayTtsWarmup",
        daemon=True,
    ).start()

    threading.Thread(
        target=component_supervisor_loop,
        args=(config,),
        name="FridayComponentSupervisor",
        daemon=True,
    ).start()

    diag(
        "STDIN_WAIT",
        force=True,
    )

    try:
        for raw_line in sys.stdin:
            if _stop_event.is_set():
                break

            try:
                raw_line = raw_line.strip()

                if not raw_line:
                    continue

                event = json.loads(raw_line)

                if not isinstance(event, dict):
                    diag(
                        "DROP_EVENT_NOT_OBJECT",
                        force=True,
                    )
                    continue

                event["_worker_received_at_ms"] = time.time() * 1000.0

                event_type = event.get("type")
                if event_type in {"wake_probe", "wake_probe_end"}:
                    target_queue = _wake_probe_queue
                elif event_type in {"speak", "text_command"}:
                    target_queue = _control_event_queue
                else:
                    target_queue = _event_queue
                try:
                    target_queue.put_nowait(event)
                except queue.Full:
                    try:
                        target_queue.get_nowait()
                        target_queue.task_done()
                    except queue.Empty:
                        pass
                    diag("EVENT_QUEUE_OLDEST_DROPPED", force=True)
                    target_queue.put_nowait(event)

            except Exception as exc:
                send_error(
                    "event_processing_error",
                    f"{type(exc).__name__}: {exc}",
                )

    finally:
        shutdown()

    return 0


if __name__ == "__main__":
    if "--gigaam-server" in sys.argv:
        raise SystemExit(gigaam_server_main())
    raise SystemExit(main())

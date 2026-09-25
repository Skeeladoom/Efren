"""Shared log rendering extracted from the legacy journal; no UI side effects."""
import re
import json
from datetime import datetime, timedelta
from assistant_identity import display_names, names as assistant_names
from control_panel_v0120_JARVIS import FRIDAY_USER_NAMES, FRIDAY_DIAG_NAMES, FRIDAY_EVENT_NAMES

detail_labels = {
    "text": "текст", "command": "команда", "result": "результат",
    "error": "ошибка", "render_ms": "создание голоса, мс",
    "playback_queue_ms": "очередь звука, мс",
    "feedback_to_sound_ms": "всего до звука, мс",
    "cache_hit": "готовая фраза из кэша",
    "speech_queue_wait_ms": "ожидание очереди TTS, мс",
    "gpu_wait_ms": "ожидание видеокарты, мс",
    "render_lock_wait_ms": "ожидание рендера, мс",
    "tts_prepare_ms": "подготовка текста, мс",
    "base_tts_ms": "базовый TTS, мс",
    "base_tts_recovery_ms": "восстановление базового TTS, мс",
    "rvc_infer_ms": "RVC-инференс, мс",
    "rvc_recovery_ms": "восстановление RVC, мс",
    "rvc_total_ms": "RVC всего, мс", "cache_io_ms": "кэш WAV, мс",
    "worker_total_ms": "обработчик TTS всего, мс",
}

def event_person(event):
    user_id = event.get("user_id")
    return (
        FRIDAY_USER_NAMES.get(str(user_id), "Неизвестный участник")
        if user_id else "Система"
    )

def diagnostic_parts(event):
    value = str(event.get("text", ""))
    if not value.startswith("[DIAG] "):
        return "", ""
    stage, _, details = value[7:].partition(" | ")
    return stage, details

def recognized_context(event):
    stage, details = diagnostic_parts(event)
    if stage != "STT_RESULT" or "text=" not in details:
        return ""
    value = details.split("text=", 1)[1].split(" | ", 1)[0].strip()
    return "" if value in {"", "<EMPTY>"} else value

def format_event_timestamp(value):
    raw_value = str(value or "").strip()
    try:
        stamp_value = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
        return stamp_value.strftime("%d.%m.%Y %H:%M:%S")
    except (TypeError, ValueError):
        fallback = raw_value[:19].replace("T", " ")
        return fallback or "--.--.---- --:--:--"

def format_friday_event(event, raw_line=""):
    if not isinstance(event, dict):
        return raw_line
    kind = str(event.get("type", "event")).upper()
    stamp = format_event_timestamp(event.get("timestamp"))
    person = event_person(event)
    stage, message = diagnostic_parts(event)
    if stage:
        if stage not in FRIDAY_DIAG_NAMES:
            return None
        kind_label = display_names(FRIDAY_DIAG_NAMES[stage])
        for raw_name, visible_name in {
            "text": "текст", "command": "команда",
            "seconds": "длительность", "minimum": "минимум",
            "source": "путь", "audio_ms": "длина фразы",
            "receiver_ms": "завершение записи",
            "bridge_ms": "передача обработчику", "queue_ms": "очередь",
            "stt_ms": "распознавание", "parse_ms": "разбор команды",
            "discord_ms": "действие Discord",
            "end_to_action_ms": "от конца фразы до действия",
            "end_to_feedback_ms": "до постановки ответа",
        }.items():
            message = re.sub(
                rf"\b{re.escape(raw_name)}=", f"{visible_name}: ", message
            )
        return (
            f"[{stamp}] {person} — {kind_label}"
            + (f": {message}" if message else "")
        )
    kind_label = display_names(FRIDAY_EVENT_NAMES.get(kind, kind.replace("_", " ")))
    kind_label = re.sub(r"\bFRIDAY\b", lambda _: assistant_names()["friday"], kind_label)
    details = []
    for key, label in detail_labels.items():
        value = event.get(key)
        if value not in (None, ""):
            # User speech stays verbatim; only generated service text is renamed.
            if key == "text" and kind in {"OUTPUT", "FRIDAY_SPEECH_PLAYING"}:
                value = re.sub(r"голос JARVIS\b", lambda _: "голос " + assistant_names()["friday"], str(value))
                value = display_names(value)
            details.append(f"{label}: {value}")
    return f"[{stamp}  {person}  {kind_label}] " + " | ".join(details)

def cutoff_for(period):
    now = datetime.now().astimezone()
    return {
        "Последние 5 минут": now - timedelta(minutes=5),
        "Последние 15 минут": now - timedelta(minutes=15),
        "Последние 30 минут": now - timedelta(minutes=30),
        "Последний час": now - timedelta(hours=1),
        "Сегодня": now.replace(hour=0, minute=0, second=0, microsecond=0),
    }.get(period)

def event_is_recent(event, cutoff):
    if cutoff is None:
        return True
    try:
        stamp = datetime.fromisoformat(str(event.get("timestamp", "")))
        if stamp.tzinfo is None:
            stamp = stamp.astimezone()
        return stamp >= cutoff
    except (TypeError, ValueError):
        return False

def event_matches_kind(event, selected_kind):
    kind = str(event.get("type", "")).upper()
    stage, _details = diagnostic_parts(event)
    if selected_kind == "Обычный разговор":
        return bool(recognized_context(event))
    if selected_kind == "Команды":
        return kind == "COMMAND" or stage in {
            "WAKE_FOUND", "NO_COMMAND_WORD", "COMMAND_DUPLICATE",
        }
    if selected_kind == "Ошибки":
        return kind == "ERROR" or "ERROR" in kind or "LOST" in stage
    return True

def filter_history(raw_lines, spec, limit=1500):
    rendered = []
    context = []
    matched = 0
    cutoff = cutoff_for(spec["period"])
    query = spec["query"].casefold()
    for raw_line in raw_lines:
        try:
            event = json.loads(raw_line)
        except (TypeError, ValueError):
            continue
        if not isinstance(event, dict):
            continue
        person = event_person(event)
        if spec["person"] != "Все участники" and person != spec["person"]:
            continue
        if not event_is_recent(event, cutoff):
            continue
        if not event_matches_kind(event, spec["kind"]):
            continue
        line = format_friday_event(event, raw_line)
        if not line or (query and query not in line.casefold()):
            continue
        matched += 1
        rendered.append(line)
        spoken = recognized_context(event)
        if spoken:
            context.append(f"[{format_event_timestamp(event.get('timestamp'))}] {person}: {spoken}")
    return rendered[-limit:], context[-3000:], matched

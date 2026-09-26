"""Backend for native journals, member controls and macro editor. No UI startup."""
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path
import control_panel_v0120_JARVIS as panel
import panel_log_format as logs


def read_logs(request):
    source = request.get("source", "friday")
    if source not in {"friday", "jarvis"}:
        raise ValueError("Неизвестный журнал")
    path = panel.FRIDAY_LOG_FILE if source == "friday" else panel.JARVIS_LOG_FILE
    live = bool(request.get("live", True))
    try:
        raw = panel.read_log_tail(path, max_lines=500 if live else 100000, max_bytes=1024**2 if live else 64 * 1024**2)
    except FileNotFoundError:
        raw = []
    spec = {"query": str(request.get("query", ""))[:400], "period": request.get("period", "Вся история"),
            "person": request.get("person", "Все участники"), "kind": request.get("kind", "Все события")}
    people = sorted(set(panel.FRIDAY_USER_NAMES.values()))
    if source == "friday":
        if request.get("context"):
            spec["kind"] = "Обычный разговор"
        if live:
            lines = []
            for line in raw:
                try: event = json.loads(line)
                except ValueError: event = None
                rendered = logs.format_friday_event(event, line)
                if rendered: lines.append(rendered)
            count = len(lines)
        else:
            lines, context, count = logs.filter_history(raw, spec)
            if request.get("context"): lines = context
    else:
        lines = []
        for line in raw:
            try: event = json.loads(line)
            except ValueError:
                if not spec["query"] or spec["query"].casefold() in line.casefold(): lines.append(line)
                continue
            if not isinstance(event, dict): continue
            if not live and not logs.event_is_recent(event, logs.cutoff_for(spec["period"])): continue
            kind = str(event.get("type", "event")).upper()
            selected_kind = str(spec.get("kind", ""))
            if "Команды" in selected_kind and not (event.get("accepted") is True or kind in {"RESULT", "COMMAND_RESULT"}): continue
            if "Ошибки" in selected_kind and kind not in {"ERROR", "EXCEPTION"} and not event.get("error"): continue
            if "Обычный" in selected_kind and (event.get("accepted") is True or kind in {"RESULT", "COMMAND_RESULT", "ERROR", "EXCEPTION"}): continue
            details = []
            for key in ("text", "wake", "command", "result", "error", "device", "model", "samplerate", "blocksize", "stt"):
                value = event.get(key)
                if value not in (None, "", False):
                    details.append(f"{panel.JARVIS_FIELD_NAMES.get(key, key)}: {panel.JARVIS_VALUE_NAMES.get(str(value).casefold(), value)}")
            if "accepted" in event: details.append("команда принята: " + ("да" if event["accepted"] else "нет"))
            rendered = f"[{logs.format_event_timestamp(event.get('timestamp'))}] {logs.display_names(panel.JARVIS_EVENT_NAMES.get(kind, kind))} | " + " | ".join(details)
            if live or spec["query"].casefold() in rendered.casefold(): lines.append(rendered)
        count = len(lines); lines = lines[-1500:]
    return {"text": "\n".join(lines), "count": count, "shown": len(lines), "people": people, "path": str(path)}


def members(request):
    operation = request.get("operation", "read")
    response = panel.discord_bridge_request("/members", timeout=8)
    if response.get("ok") is False: raise RuntimeError(response.get("error", "Не удалось получить участников"))
    people = response.get("members", [])
    if operation == "read": return {"members": people}
    uid = str(request.get("userId", ""))
    member = next((m for m in people if str(m.get("id")) == uid), None)
    if member is None: raise ValueError("Участник больше не найден; обновите список.")
    if member.get("protected"): raise ValueError("Участник защищён; действие не выполнено.")
    if operation == "role":
        role = request.get("permission")
        if role not in {"vip", "trusted", "standard", "prankster", "blocked"}: raise ValueError("Неизвестная роль")
        result = panel.discord_bridge_request("/member-permission", "POST", {"userId": uid, "permission": role}, timeout=5)
    elif operation == "voice":
        action = request.get("voice_action")
        if action not in {"mute", "unmute", "deaf", "undeaf", "disconnect"}: raise ValueError("Неизвестное действие")
        if not member.get("inVoice"): raise ValueError("Участник уже вышел из войса.")
        result = panel.discord_bridge_request("/voice/member-action", "POST", {"userId": uid, "action": action}, timeout=7)
    else: raise ValueError("Неизвестное действие")
    if result.get("ok") is False: raise RuntimeError(result.get("error", "Действие не выполнено"))
    return {"done": True}


_plans = {}
_job = {"running": False, "message": "Макрос не запущен"}
_job_lock = threading.Lock()


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def macros(request):
    import macro_runner as macro  # No model is loaded; import only when opening the constructor.
    operation = request.get("operation")
    disabled_path = panel.BASE_DIR / "macro_disabled.json"
    if operation in {"registry", "registry_toggle", "registry_delete"}:
        registry = json.loads(macro.PHRASES_FILE.read_text(encoding="utf-8")) if macro.PHRASES_FILE.exists() else {}
        disabled = json.loads(disabled_path.read_text(encoding="utf-8")) if disabled_path.exists() else []
        if not isinstance(registry, dict) or not isinstance(disabled, list):
            raise ValueError("Повреждён список голосовых команд")
        phrase = str(request.get("phrase", "")).strip()
        if operation == "registry_toggle":
            if phrase not in registry: raise ValueError("Команда больше не найдена")
            if phrase in disabled: disabled.remove(phrase)
            else: disabled.append(phrase)
            atomic_json(disabled_path, sorted(set(disabled)))
        elif operation == "registry_delete":
            if phrase not in registry: raise ValueError("Команда больше не найдена")
            del registry[phrase]
            atomic_json(macro.PHRASES_FILE, registry)
            if phrase in disabled:
                disabled.remove(phrase); atomic_json(disabled_path, disabled)
        return {"commands": [{"phrase": key, "path": str(value), "enabled": key not in disabled,
                              "exists": Path(str(value)).is_file()} for key, value in sorted(registry.items())]}
    if operation == "windows":
        return {"windows": [{"id": str(hwnd), "title": title} for hwnd, title in macro.visible_windows()]}
    if operation == "status":
        with _job_lock: return dict(_job)
    if operation == "load":
        path = Path(str(request.get("path", "")))
        if path.suffix.lower() != ".jmacro": raise ValueError("Нужен файл .jmacro")
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc.get("формат") not in {"JARVIS-MACRO-1", "JARVIS-MACRO-2"}: raise ValueError("Неизвестный формат")
        macro._validate(doc.get("действия", []))
        return {"document": doc}
    if operation == "plan":
        kind = request.get("kind", "launch")
        if kind not in {"launch", "macro"}: raise ValueError("Неизвестный режим")
        target = str(request.get("target", "")).strip().strip('"')
        title = str(request.get("title", ""))
        prompt = str(request.get("prompt", ""))
        if len(prompt) > 20000: raise ValueError("План слишком большой")
        if kind == "launch":
            p = Path(target)
            if not p.is_file() or p.suffix.lower() not in {".exe", ".lnk", ".url"}: raise ValueError("Выберите приложение или ярлык")
            actions = []
        else:
            # Imported JSON supports repeat/nested actions from old .jmacro files.
            actions = macro._validate(json.loads(prompt)) if prompt.lstrip().startswith("[") else macro.explicit_plan(prompt)
            if not actions: raise ValueError("Пустой план")
            if any(x in (target + " " + title + " " + prompt).casefold() for x in macro.ONLINE_MARKERS):
                raise ValueError("Нажатия в сетевых играх запрещены; простой запуск доступен.")
        doc = {"формат": "JARVIS-MACRO-2", "тип": kind, "название": str(request.get("name", "Новый сценарий")),
               "кодовая_фраза": macro.normalize_phrase(request.get("phrase", "")), "окно": title, "файл": target, "действия": actions}
        token = uuid.uuid4().hex
        if len(_plans) >= 20: _plans.pop(next(iter(_plans)))
        _plans[token] = (doc, str(request.get("hwnd", "")))
        return {"token": token, "preview": json.dumps(doc, ensure_ascii=False, indent=2)}
    token = request.get("token")
    if token not in _plans: raise ValueError("Сначала проверьте план заново.")
    doc, hwnd = _plans[token]
    if operation == "save":
        path = Path(str(request.get("path", ""))).resolve()
        if path.suffix.lower() != ".jmacro": raise ValueError("Сохраните как .jmacro")
        # Preserve a broken registry rather than silently replacing it.
        registry = json.loads(macro.PHRASES_FILE.read_text(encoding="utf-8")) if macro.PHRASES_FILE.exists() else {}
        if not isinstance(registry, dict): raise ValueError("Повреждён список кодовых фраз")
        atomic_json(path, doc)
        if doc["кодовая_фраза"]:
            registry[doc["кодовая_фраза"]] = str(path)
            atomic_json(macro.PHRASES_FILE, registry)
        return {"message": "Сценарий сохранён" + ("; кодовая фраза привязана." if doc["кодовая_фраза"] else ".")}
    if operation != "run": raise ValueError("Неизвестное действие")
    with _job_lock:
        if _job["running"]: raise ValueError("Макрос уже выполняется")
        _job.update(running=True, message="Запуск…")
    def work():
        try:
            if doc["тип"] == "launch": macro.launch_application(doc["файл"])
            else:
                candidates = macro.visible_windows()
                wanted = next((h for h, t in candidates if str(h) == hwnd and t == doc["окно"]), None)
                if wanted is None:
                    matches = [h for h, t in candidates if t == doc["окно"] and t]
                    if len(matches) == 1: wanted = matches[0]
                if wanted is None and doc["файл"]:
                    macro.launch_application(doc["файл"]); time.sleep(3)
                    matches = [h for h, t in macro.visible_windows() if t == doc["окно"] and t]
                    if len(matches) == 1: wanted = matches[0]
                if not wanted or not macro.activate_window(wanted):
                    raise RuntimeError("Не найдено однозначное целевое окно. Выберите его; нажатия не отправлены.")
                time.sleep(0.7)
                def execute(actions):
                    for action in actions:
                        if macro.ctypes.windll.user32.GetForegroundWindow() != wanted:
                            raise RuntimeError("Фокус ушёл с выбранного окна; макрос остановлен.")
                        if action["действие"] == "повтор":
                            for _ in range(action["раз"]): execute(action["шаги"])
                        else: macro.run_actions([action])
                execute(doc["действия"])
            message = "Готово."
        except Exception as exc: message = "Ошибка: " + str(exc)
        with _job_lock: _job.update(running=False, message=message)
    threading.Thread(target=work, name="PanelMacro", daemon=True).start()
    return {"message": "Запуск запрошен. Для остановки нажатий — мышь в левый верхний угол."}


def dispatch(request):
    action = request["action"]
    if action == "logs": return read_logs(request)
    if action == "members": return members(request)
    if action == "macros": return macros(request)
    raise ValueError("Неизвестная функция")

"""Private stdio adapter for the WPF panel. No network listener or AI models."""
import hashlib
import hmac
import json
import os
import subprocess
import sys
import queue
import threading
import zipfile
import time
import ctypes
import shutil
import contextlib
from pathlib import Path

import assistant_identity as identity
import control_panel_v0120_JARVIS as panel
from lite_policy import is_lite, check_request

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
BOOL_SETTINGS = {"voice_enabled", "tts_enabled", "discord_commands_enabled",
                 "windows_commands_enabled", "browser_clarification_enabled",
                 "friends_voice_enabled", "friends_can_use_discord", "ui_sounds_enabled"}
WINDOWS = {"friday_log": "open_friday_log", "jarvis_log": "open_jarvis_log",
           "roles": "open_member_permissions", "training": "open_recognition_training",
           "diagnostics": "open_diagnostics"}
window_requests = queue.Queue()
lite_console = None


def jarvis_voice_status(root):
    """Return a short user-facing summary without loading any voice model."""
    root = Path(root)
    try:
        config = json.loads((root / "config.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, TypeError):
        return "Голос: Piper (базовый)"
    model_value = str(config.get("rvc_model", "")).strip()
    if not model_value:
        return "Голос: Piper (базовый)"
    model = Path(model_value)
    if not model.is_absolute(): model = root / model
    name = model.stem
    try:
        metadata = json.loads((model.parent / "voice.json").read_text(encoding="utf-8"))
        name = str(metadata.get("name") or name)
    except (OSError, ValueError, TypeError):
        pass
    if not config.get("rvc_enabled", False):
        return "Голос: Piper · выбран «" + name + "», но RVC выключен"
    try:
        runtime = json.loads((root / "runtime/rvc-status.json").read_text(encoding="utf-8"))
        state = str(runtime.get("state", "")) if str(runtime.get("model", "")) == model.stem else ""
        if state == "fallback":
            return "Голос: Piper · «" + name + "» не успел обработать реплику"
        if state == "loading":
            return "Голос: «" + name + "» · загружается RVC…"
    except (OSError, ValueError, TypeError):
        pass
    device = str(config.get("rvc_device", "cpu")).lower()
    mode = ("Nvidia CUDA" if device == "cuda" else
            "видеоядро / DirectML" if device == "directml" else
            "CPU, " + str(config.get("rvc_cpu_threads", 4)) + " потока")
    return "Голос: «" + name + "» · " + mode


def lite_console_action(value, mode):
    global lite_console
    # The stdout pipe is a JSON protocol: assistant diagnostics must go to stderr.
    with contextlib.redirect_stdout(sys.stderr):
        import main
        from voice import VoiceListener
        if lite_console is None:
            lite_console = main.Jarvis()
        if mode == "speech":
            if not lite_console.tts_enabled():
                raise ValueError("Включите озвучку ответов в настройках.")
            if not lite_console.tts.enabled:
                raise RuntimeError("Озвучка не готова. Проверьте компоненты Piper.")
            lite_console.tts.say(value)
            answer = "Текст передан на озвучивание."
        else:
            _state, answer = lite_console.handle(value)
            main.speak_answer(lite_console, answer)
        VoiceListener._write_log("COMMAND", text=value, command=value, result=answer)
    return {"accepted": True, "result": answer}


def spawn(args, cwd=None):
    return subprocess.Popen([str(x) for x in args], cwd=str(cwd or panel.BASE_DIR),
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)


def status():
    lite = is_lite(panel.BASE_DIR)
    health = {} if lite else (panel.discord_bridge_identity() or {})
    pid = None if lite else panel.read_jarvis_pid()
    if lite:
        from lite_runtime import owned_process, process_state
        process = owned_process(panel.BASE_DIR)
        pid = process.pid if process else None
    return {"names": identity.names(), "settings": panel.load_settings(), "browsers": panel.BROWSER_LABELS,
            "friday": health.get("friday", {}), "bridge": bool(health),
            "edition": "lite" if lite else "full",
            "first_run": lite and not (panel.BASE_DIR / "lite-auth.json").exists(),
            "startup_enabled": __import__("lite_runtime").startup_file(panel.BASE_DIR).exists() if lite else panel.control_center_startup_file().with_name("EFREN_WPF.lnk").exists(),
            "legacy_startup": False if lite else panel.control_center_startup_file().exists(),
            "jarvis_running": bool(pid and panel.process_exists(pid)),
            "jarvis_state": process_state(panel.BASE_DIR) if lite else ("running" if pid and panel.process_exists(pid) else "stopped"),
            "jarvis_pid": pid, "backend_pid": os.getpid(),
            "jarvis_voice_status": jarvis_voice_status(panel.BASE_DIR)}


def lite_backup(request):
    if not is_lite(panel.BASE_DIR):
        raise ValueError("Резервные копии доступны только в EFREN Lite.")
    operation = request.get("operation")
    archive = Path(str(request.get("path", ""))).resolve()
    if archive.suffix.lower() != ".zip":
        raise ValueError("Выберите ZIP-файл резервной копии.")
    files = ["assistant_names.json", "jarvis_settings.json", "panel_theme.json",
             "macro_phrases.json", "macro_disabled.json"]
    if operation == "export":
        archive.parent.mkdir(parents=True, exist_ok=True)
        temporary = archive.with_suffix(".tmp")
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as output:
            output.writestr("backup-manifest.json", json.dumps({"format": "EFREN-LITE-BACKUP-1"}, ensure_ascii=False))
            for name in files:
                source = panel.BASE_DIR / name
                if source.is_file(): output.write(source, name)
            for folder in ("сценарии", "scenarios"):
                source = panel.BASE_DIR / folder
                if source.is_dir():
                    for item in source.rglob("*.jmacro"):
                        if item.is_file(): output.write(item, item.relative_to(panel.BASE_DIR))
        os.replace(temporary, archive)
        return {"message": "Резервная копия создана: " + str(archive)}
    if operation != "import": raise ValueError("Неизвестная операция резервной копии.")
    if not archive.is_file(): raise FileNotFoundError("Резервная копия не найдена.")
    with zipfile.ZipFile(archive, "r") as source:
        entries = source.infolist()
        if len(entries) > 500 or sum(x.file_size for x in entries) > 20 * 1024 * 1024:
            raise ValueError("Резервная копия слишком большая или содержит слишком много файлов.")
        manifest = json.loads(source.read("backup-manifest.json").decode("utf-8"))
        if manifest.get("format") != "EFREN-LITE-BACKUP-1": raise ValueError("Неизвестный формат резервной копии.")
        allowed = set(files)
        restored = 0
        for entry in entries:
            name = entry.filename.replace("\\", "/")
            parts = Path(name).parts
            valid_scenario = len(parts) >= 2 and parts[0] in {"сценарии", "scenarios"} and name.lower().endswith(".jmacro")
            if name not in allowed and not valid_scenario: continue
            if entry.is_dir() or entry.file_size > 5 * 1024 * 1024 or ".." in parts: raise ValueError("Недопустимый файл в резервной копии.")
            target = (panel.BASE_DIR / Path(*parts)).resolve()
            if panel.BASE_DIR.resolve() not in target.parents: raise ValueError("Недопустимый путь в резервной копии.")
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(target.suffix + ".restore.tmp")
            temporary.write_bytes(source.read(entry))
            os.replace(temporary, target); restored += 1
    return {"message": "Восстановлено файлов: " + str(restored) + ". Перезапустите панель."}


def bot_action(operation):
    if operation in {"stop", "restart"}:
        pids = panel.find_discord_bot_pids()
        stopped = panel.terminate_discord_bot_pids(pids)
        if len(stopped) != len(pids):
            raise RuntimeError("Не удалось остановить подтверждённые процессы бота.")
        panel.BOT_PID_FILE.unlink(missing_ok=True)
    if operation in {"start", "restart"}:
        if panel.discord_bridge_online() or panel.find_discord_bot_pids():
            return "Процесс уже запущен"
        env = os.environ.copy()
        env["FRIDAY_PROJECT_DIR"] = str(panel.BASE_DIR)
        env["FRIDAY_PYTHON_EXE"] = str(panel.worker_python_path())
        process = subprocess.Popen([str(panel.NODE_EXE), str(panel.DISCORD_BOT_FILE)],
                                   cwd=str(panel.DISCORD_BOT_DIR), env=env,
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
        panel.BOT_PID_FILE.write_text(str(process.pid), encoding="utf-8")
    return "Готово"


def jarvis_action(operation):
    if is_lite(panel.BASE_DIR):
        from lite_runtime import jarvis_action as lite_action
        return lite_action(panel.BASE_DIR, operation)
    pid = panel.read_jarvis_pid()
    verified = bool(pid and (panel.managed_jarvis_pid(pid) or panel.process_matches_jarvis(pid)))
    if operation in {"stop", "restart"} and verified:
        result = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                                capture_output=True, creationflags=CREATE_NO_WINDOW)
        if result.returncode and panel.process_exists(pid):
            raise RuntimeError("Windows не завершила процесс помощника.")
        panel.JARVIS_PID_FILE.unlink(missing_ok=True)
        verified = False
    if operation in {"start", "restart"} and not verified:
        process = spawn([panel.pythonw_path(), panel.MAIN_FILE, "--resident"])
        panel.JARVIS_PID_FILE.write_text(str(process.pid), encoding="utf-8")
    return "Готово"


def training(request):
    path = panel.FRIDAY_RECOGNITION_ALIASES_FILE
    document = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"replacements": {}}
    if not isinstance(document, dict):
        raise ValueError("Некорректный словарь исправлений; файл не изменён.")
    items = document.get("replacements", document)
    if not isinstance(items, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in items.items()):
        raise ValueError("Некорректные записи словаря; файл не изменён.")
    operation = request.get("operation", "read")
    if operation not in {"read", "save", "delete"}:
        raise ValueError("Неизвестное действие со словарём.")
    if operation != "read":
        wrong = request.get("wrong")
        if not isinstance(wrong, str):
            raise ValueError("Не указана ошибочная фраза.")
        if operation == "save":
            correct = request.get("correct")
            if not isinstance(correct, str):
                raise ValueError("Не указано исправление.")
            wrong, correct = " ".join(wrong.lower().split()), " ".join(correct.lower().split())
            if len(wrong) < 2 or not correct or wrong == correct or max(len(wrong), len(correct)) > 400:
                raise ValueError("Нужны две разные фразы длиной до 400 символов.")
            items[wrong] = correct
        else:
            if wrong not in items:
                raise ValueError("Запись уже удалена. Обновите список.")
            del items[wrong]
        if "replacements" in document:
            document["replacements"] = items
        temporary = path.with_suffix(".wpf.tmp")
        temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    recent = []
    for raw in reversed(panel.read_log_tail(panel.FRIDAY_LOG_FILE, max_lines=3000, max_bytes=5 * 1024 * 1024)):
        try:
            event = json.loads(raw)
            text = str(event.get("text", ""))
        except (ValueError, TypeError, AttributeError):
            continue
        if not text.startswith("[DIAG] ") or not any(x in text for x in ("NO_COMMAND_WORD", "NO_WAKE")):
            continue
        value = text.split("command=", 1)[-1] if "command=" in text else text.split("text=", 1)[-1]
        value = value.split(" | ", 1)[0].strip()
        if value and value not in recent:
            recent.append(value)
        if len(recent) >= 80:
            break
    return {"replacements": items, "recent": recent}


def voice_files_status():
    """Check configured Friday assets without importing/loading a voice model."""
    try:
        config = json.loads((panel.BASE_DIR / "config.json").read_text(encoding="utf-8-sig"))
        if not config.get("friday_rvc_enabled", config.get("rvc_enabled", True)):
            return ["Преобразование голоса RVC: отключено"]
        result = []
        for key, label in (("rvc_model", "Голосовая модель"), ("rvc_index", "Индекс голоса")):
            value = str(config.get("friday_" + key, config.get(key, ""))).strip()
            path = Path(value)
            if not path.is_absolute(): path = panel.BASE_DIR / path
            result.append(label + ": " + (path.name + " — файл на месте" if value and path.is_file()
                                          else "файл не найден" if value else "не задан"))
        return result
    except (OSError, ValueError, TypeError, AttributeError):
        return ["Файлы голоса: не удалось прочитать конфигурацию"]


def diagnostics():
    started = time.perf_counter()
    try:
        health = panel.discord_bridge_request("/health", timeout=3.0)
    except Exception:
        health = {}
    friday = health.get("friday", {})
    lines = [f"Локальный мост: {'работает' if health else 'не отвечает'}",
             f"Ответ моста: {round((time.perf_counter() - started) * 1000)} мс" if health else "Ответ моста: нет данных",
             "Discord: " + ("подключён" if health.get("discordReady") else "нет связи"),
             "Распознавание: " + ("готово" if friday.get("workerReady") else "не готово / загружается"),
             "Голосовой канал: " + str(friday.get("voiceStatus", "нет данных")),
             "Озвучка: " + ("готова по статусу обработчика" if friday.get("ttsReady") else "не готова / загружается"),
             identity.names()["jarvis"] + ": " + ("запущен" if panel.managed_jarvis_pid(panel.read_jarvis_pid()) else "выключен")]
    lines.extend(voice_files_status())
    class MemoryStatus(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [(name, ctypes.c_ulonglong) for name in ("total", "available", "page_total", "page_available", "virtual_total", "virtual_available", "extended")]
    memory = MemoryStatus(); memory.length = ctypes.sizeof(memory)
    try:
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
            raise OSError("memory unavailable")
        lines.append(f"Оперативная память: занято {memory.load}%, свободно {memory.available / 1024**3:.1f} ГБ")
    except (OSError, AttributeError):
        lines.append("Оперативная память: нет данных")
    for drive in dict.fromkeys(("C:\\", panel.BASE_DIR.anchor)):
        try:
            lines.append(f"Диск {drive}: свободно {shutil.disk_usage(drive).free / 1024**3:.1f} ГБ")
        except OSError:
            lines.append(f"Диск {drive}: нет данных")
    stats = panel.JarvisControlPanel._friday_recognition_stats()
    words = ", ".join(f"{word} ({count})" for word, count in stats["problem_words"]) or "недостаточно данных"
    report = (f"Проанализировано фраз: {stats['recognized']}\nВыполнено команд: {stats['commands']}\n"
              f"Пустых распознаваний: {stats['empty']}\nНе найдено обращение: {stats['no_wake']}\n"
              f"Не распознана команда: {stats['no_command']}\nСреднее распознавание: {stats['average_ms']:.0f} мс\n\n"
              f"Частые слова в нераспознанных командах:\n{words}")
    return {"system": "\n".join(lines), "recognition": report}


def dispatch(request):
    global lite_console
    check_request(request, is_lite(panel.BASE_DIR))
    action = request.get("action")
    if action in {"logs", "members", "macros", "voice_store"}:
        import panel_features
        return panel_features.dispatch(request)
    if action == "status":
        return status()
    if action == "journal_settings":
        values = panel.load_settings().get("friday_favorite_commands", [])
        return {"favorites": [value for value in values if isinstance(value, str)][:8]}
    if action == "training":
        return training(request)
    if action == "diagnostics":
        if is_lite(panel.BASE_DIR):
            from lite_runtime import diagnostics as lite_diagnostics
            return lite_diagnostics(panel.BASE_DIR)
        return diagnostics()
    if action == "repair":
        try:
            health = panel.discord_bridge_request("/health", timeout=2.5)
        except Exception:
            health = {}
        if not health.get("friday", {}).get("workerReady"):
            bot_action("restart")
            return {"message": "Мост или распознавание не готовы. Отправлен перезапуск Discord-помощника; дождитесь готовности."}
        result = panel.discord_bridge_request("/friday/repair-components", "POST", {}, timeout=5)
        if result.get("ok") is False:
            raise RuntimeError(result.get("error", "Не удалось запустить восстановление"))
        return {"message": "Запущена проверка компонентов. Восстановится только неисправная часть."}
    if action == "favorite":
        operation, value = request.get("operation"), request.get("text")
        if operation not in {"add", "remove"} or not isinstance(value, str) or not 1 <= len(value.strip()) <= 400:
            raise ValueError("Нужна команда длиной от 1 до 400 символов.")
        value = value.strip()
        settings = panel.load_settings()
        values = list(settings.get("friday_favorite_commands", []))
        if operation == "add" and value not in values:
            if len(values) >= 8:
                raise ValueError("В избранном уже 8 команд. Сначала удалите одну.")
            values.append(value)
        if operation == "remove":
            values = [item for item in values if item != value]
        settings["friday_favorite_commands"] = values
        temporary = panel.SETTINGS_FILE.with_suffix(".wpf.tmp")
        temporary.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, panel.SETTINGS_FILE)
        return {"saved": True}
    if action == "full_shutdown":
        settings = panel.load_settings()
        for key in ("voice_enabled", "tts_enabled", "discord_commands_enabled", "windows_commands_enabled", "friends_voice_enabled", "friends_can_use_discord"):
            settings[key] = False
        settings["qwen_mode"] = "disabled"
        temporary = panel.SETTINGS_FILE.with_suffix(".wpf.tmp")
        temporary.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, panel.SETTINGS_FILE)
        errors = []
        stops = (("Jarvis", jarvis_action),) if is_lite(panel.BASE_DIR) else (("Discord", bot_action), ("Jarvis", jarvis_action))
        if is_lite(panel.BASE_DIR) and lite_console is not None:
            lite_console.tts.stop()
            lite_console = None
        for name, stop in stops:
            try:
                stop("stop")
            except Exception as exc:
                errors.append(f"{name}: {exc}")
        if errors:
            raise RuntimeError("Функции отключены в настройках, но не всё удалось остановить: " + "; ".join(errors))
        return {"stopped": True}
    if action == "console":
        value = request.get("text")
        mode = request.get("mode")
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > 400:
            raise ValueError("Введите от 1 до 400 символов.")
        if mode not in {"command", "speech"}:
            raise ValueError("Неизвестный режим отправки.")
        if is_lite(panel.BASE_DIR):
            return lite_console_action(value.strip(), mode)
        result = (panel.request_friday_command(value.strip()) if mode == "command"
                  else panel.request_friday_speech(value.strip()))
        if not result.get("ok"):
            raise RuntimeError(result.get("error", "Запрос не принят"))
        return {"accepted": True}
    if action == "reply_mode":
        group, mode = request.get("group"), request.get("mode")
        if group not in {"default", "disconnect", "self_disconnect", "random_disconnect", "genocide"}:
            raise ValueError("Неизвестная группа команд.")
        if mode not in {"voice", "sound", "log", "none"} or (group == "default" and mode == "sound"):
            raise ValueError("Недопустимый способ ответа.")
        settings = panel.load_settings()
        modes = dict(settings.get("friday_reply_modes", {}))
        modes[group] = mode
        settings["friday_reply_modes"] = modes
        temporary = panel.SETTINGS_FILE.with_suffix(".wpf.tmp")
        temporary.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, panel.SETTINGS_FILE)
        return {"saved": True}
    if action == "startup":
        enabled = request.get("enabled")
        if not isinstance(enabled, bool):
            raise ValueError("Ожидалось включение или отключение автозапуска.")
        legacy = panel.control_center_startup_file()
        shortcut = legacy.with_name("EFREN_WPF.lnk")
        lite = is_lite(panel.BASE_DIR)
        if lite:
            from lite_runtime import startup_file
            shortcut = startup_file(panel.BASE_DIR)
        if enabled:
            exe = panel.BASE_DIR / "panel-wpf" / "bin" / "FridayPanel.exe"
            if not exe.is_file():
                raise FileNotFoundError("Не найдена новая панель.")
            shortcut.parent.mkdir(parents=True, exist_ok=True)
            quote = lambda value: "'" + str(value).replace("'", "''") + "'"
            script = ("$ErrorActionPreference='Stop'; $s=New-Object -ComObject WScript.Shell; "
                      "$l=$s.CreateShortcut(" + quote(shortcut) + "); "
                      "$l.TargetPath=" + quote(exe) + "; $l.WorkingDirectory=" + quote(panel.BASE_DIR) + "; $l.Save()")
            subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                           capture_output=True, check=True, timeout=15, creationflags=CREATE_NO_WINDOW)
            if not shortcut.exists():
                raise RuntimeError("Ярлык автозапуска не создан.")
        else:
            shortcut.unlink(missing_ok=True)
        # Only this application's known old startup entry, never other startup items.
        if not lite:
            legacy.unlink(missing_ok=True)
        return {"enabled": enabled}
    if action == "authenticate":
        if is_lite(panel.BASE_DIR):
            from lite_runtime import authenticate
            return {"authenticated": authenticate(panel.BASE_DIR, request.get("password", ""))}
        digest = hashlib.sha256(str(request.get("password", "")).encode("utf-8")).hexdigest()
        return {"authenticated": hmac.compare_digest(digest, panel.START_PASSWORD_HASH)}
    if action == "setting":
        key, value = request.get("key"), request.get("value")
        if key in BOOL_SETTINGS:
            if not isinstance(value, bool):
                raise ValueError("Настройка должна быть включена или выключена.")
        elif key == "qwen_mode":
            if value not in {"disabled", "explicit", "fallback"}:
                raise ValueError("Неизвестный режим Qwen.")
        elif key == "default_browser":
            if value not in panel.BROWSER_LABELS:
                raise ValueError("Неизвестный браузер.")
        else:
            raise ValueError("Неизвестная настройка.")
        settings = panel.load_settings()
        settings[key] = value
        temporary = panel.SETTINGS_FILE.with_suffix(".wpf.tmp")
        temporary.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, panel.SETTINGS_FILE)
        return {"saved": True}
    if action == "name":
        key = request.get("key")
        if key not in identity.DEFAULT_NAMES:
            raise ValueError("Неизвестный помощник.")
        identity.save_name(key, str(request.get("value", "")))
        return identity.names()
    if action in {"bot", "jarvis"}:
        operation = request.get("operation")
        if operation not in {"start", "stop", "restart"}:
            raise ValueError("Неизвестное действие.")
        return bot_action(operation) if action == "bot" else jarvis_action(operation)
    if action == "voice_restart":
        return panel.request_friday_voice_model_restart()
    if action == "window":
        key = request.get("window")
        if key in WINDOWS:
            done = threading.Event()
            result = []
            window_requests.put((key, done, result))
            if not done.wait(15):
                raise TimeoutError("Окно не ответило вовремя.")
            if result:
                raise RuntimeError(result[0])
        elif key == "macros":
            spawn([panel.pythonw_path(), panel.BASE_DIR / "macro_runner.py"])
        elif key == "legacy":
            spawn([panel.pythonw_path(), panel.BASE_DIR / "control_panel_v0120_JARVIS.py"])
        elif key == "chat":
            subprocess.Popen([str(panel.worker_python_path()), str(panel.MAIN_FILE), "--chat"],
                             cwd=str(panel.BASE_DIR), creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
        else:
            raise ValueError("Неизвестное окно.")
        return {"opened": True}
    if action == "project":
        os.startfile(str(panel.BASE_DIR))
        return {"opened": True}
    if action == "backup":
        return lite_backup(request)
    raise ValueError("Неизвестный запрос.")


def auxiliary_window(key):
    import tkinter as tk
    app = panel.JarvisControlPanel(auxiliary=True)
    getattr(app, WINDOWS[key])()
    def close_if_empty():
        if not any(isinstance(child, tk.Toplevel) for child in app.root.winfo_children()):
            app.sound_engine.shutdown()
            app.root.destroy()
        else:
            app.root.after(400, close_if_empty)
    app.root.after(400, close_if_empty)
    app.run()


def serve(finished=None):
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    protocol_output = sys.stdout
    if is_lite(panel.BASE_DIR):
        sys.stdout = sys.stderr
    authenticated = False
    for line in sys.stdin:
        try:
            request = json.loads(line)
            if request.get("action") not in {"status", "authenticate"} and not authenticated:
                raise PermissionError("Сначала введите пароль панели.")
            data = dispatch(request)
            if request.get("action") == "authenticate":
                authenticated = bool(data.get("authenticated"))
            response = {"ok": True, "data": data}
        except Exception as exc:
            response = {"ok": False, "error": str(exc)}
        print(json.dumps(response, ensure_ascii=False), flush=True, file=protocol_output)
    if finished is not None:
        finished.set()
    if lite_console is not None:
        lite_console.tts.stop()
    sys.stdout = protocol_output


def serve_with_windows():
    """Reuse one hidden Tk root; never rebuild the legacy panel on each click."""
    import tkinter as tk
    app = panel.JarvisControlPanel(auxiliary=True)
    finished = threading.Event()
    opened = {}
    def poll():
        if finished.is_set():
            app.sound_engine.shutdown()
            app.root.destroy()
            return
        try:
            key, done, result = window_requests.get_nowait()
        except queue.Empty:
            pass
        else:
            try:
                window = opened.get(key)
                if window is not None and window.winfo_exists():
                    window.deiconify()
                    window.lift()
                    window.focus_force()
                else:
                    app.settings = panel.load_settings()
                    before = set(app.root.winfo_children())
                    getattr(app, WINDOWS[key])()
                    children = [w for w in app.root.winfo_children()
                                if w not in before and isinstance(w, tk.Toplevel)]
                    if children:
                        opened[key] = children[0]
                    app.root.update_idletasks()
            except Exception as exc:
                result.append(str(exc))
            finally:
                done.set()
        app.root.after(30, poll)
    threading.Thread(target=serve, args=(finished,), daemon=True).start()
    app.root.after(0, poll)
    app.run()


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--window" and sys.argv[2] in WINDOWS:
        auxiliary_window(sys.argv[2])
    else:
        if is_lite(panel.BASE_DIR):
            serve()
        else:
            serve_with_windows()

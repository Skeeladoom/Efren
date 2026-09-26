"""Backend for native journals, member controls and macro editor. No UI startup."""
import json
import os
import re
import threading
import time
import uuid
import hashlib
import shutil
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path
import control_panel_v0120_JARVIS as panel
import panel_log_format as logs


HF_VOICE_REPO = "niobures/RVC-Models"
_voice_job = {"running": False, "message": "", "downloaded": 0, "total": 0, "error": False}
_voice_lock = threading.Lock()


def _voice_path(value):
    value = str(value or "").replace("\\", "/").strip("/")
    if any(part in {"", ".", ".."} for part in value.split("/")) if value else False:
        raise ValueError("Недопустимый путь каталога")
    return value


def _hf_voice_items(path):
    encoded = urllib.parse.quote(path, safe="/")
    suffix = "/" + encoded if encoded else ""
    url = f"https://huggingface.co/api/models/{HF_VOICE_REPO}/tree/main{suffix}?limit=1000"
    request = urllib.request.Request(url, headers={"User-Agent": "EFREN-Lite/0.1.5"})
    with urllib.request.urlopen(request, timeout=20) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not isinstance(result, list):
        raise ValueError("Hugging Face вернул неожиданный ответ")
    return result


def _installed_voices():
    root = panel.BASE_DIR / "rvc_models" / "store"
    active_model = ""
    try:
        config_path = panel.BASE_DIR / "config.json"
        active_model = str(json.loads(config_path.read_text(encoding="utf-8-sig")).get("rvc_model", ""))
    except (OSError, ValueError, TypeError):
        pass
    voices = []
    if root.is_dir():
        for metadata in root.glob("*/voice.json"):
            try:
                item = json.loads(metadata.read_text(encoding="utf-8"))
                item["directory"] = str(metadata.parent)
                item["installed"] = True
                item["active"] = str(metadata.parent / str(item.get("model", ""))) == active_model
                voices.append(item)
            except (OSError, ValueError, TypeError):
                continue
    return sorted(voices, key=lambda x: str(x.get("name", "")).casefold())


def _root_path(value):
    path = Path(str(value))
    return path if path.is_absolute() else panel.BASE_DIR / path


def _optimize_rvc(model, index):
    """Benchmark isolated CPU/DirectML bridges and save the fastest valid mode."""
    config_path = panel.BASE_DIR / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8-sig")) if config_path.exists() else {}
    python = panel.BASE_DIR / "runtime" / "python" / "python.exe"
    engine = panel.BASE_DIR / "rvc_engine"
    bridge = engine / "jarvis_bridge.py"
    piper = _root_path(config.get("piper_exe", "runtime/piper/piper.exe"))
    piper_model = _root_path(config.get("piper_model", "tts_models/ru_RU-ruslan-medium.onnx"))
    required = (python, bridge, engine / "assets" / "hubert_base" / "pytorch_model.bin",
                engine / "assets" / "rmvpe" / "rmvpe.pt", piper, piper_model, model)
    if not all(path.exists() for path in required):
        missing = next(path for path in required if not path.exists())
        raise FileNotFoundError("Компонент CPU-RVC неполный: " + str(missing))
    benchmark = panel.BASE_DIR / "runtime" / "rvc-benchmark.wav"
    command = [str(piper), "--model", str(piper_model), "--config", str(piper_model) + ".json",
               "--output_file", str(benchmark), "--length_scale", "1.0"]
    result = subprocess.run(command, input="Проверка скорости выбранного голоса.", text=True, encoding="utf-8",
                            capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=30)
    if result.returncode != 0 or not benchmark.is_file():
        raise RuntimeError("Не удалось создать звук для проверки RVC")
    logical = max(1, os.cpu_count() or 1)
    # Two sensible CPU points are enough; testing every thread count made the
    # first voice selection take several minutes on older processors.
    cpu_threads = [min(4, logical)]
    if not cpu_threads: cpu_threads = [1]
    candidates = [("cpu", value) for value in cpu_threads]
    # DirectML is meant here for AMD/Intel integrated graphics. On Nvidia the
    # CUDA backend is the appropriate future path; RVC over DirectML proved
    # unstable on Pascal and could hang an otherwise completed reply.
    try:
        probe = subprocess.run([str(python), "-c",
            "import torch_directml as d; print(d.device_name(d.default_device()))"],
            text=True, encoding="utf-8", errors="replace", capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=15)
        directml_name = probe.stdout.strip().casefold()
        if probe.returncode == 0 and directml_name and "nvidia" not in directml_name:
            candidates.append(("directml", min(4, logical)))
    except (OSError, subprocess.SubprocessError):
        pass
    best = None
    for number, (device, threads) in enumerate(candidates, 1):
        with _voice_lock:
            label = "видеоядро / DirectML" if device == "directml" else f"CPU, {threads} потоков"
            _voice_job.update(message="Проверка RVC: " + label + "…", downloaded=number - 1, total=len(candidates))
        output1 = benchmark.with_name(f"rvc-test-{device}-{threads}.wav")
        requests = "\n".join(json.dumps({"input": str(benchmark), "output": str(output), "method": "rmvpe",
                                          "index_rate": 0.45, "protect": 0.28, "filter_radius": 3})
                             for output in (output1,)) + "\n"
        started = time.perf_counter()
        process = subprocess.run([str(python), str(bridge), str(model), str(index), str(threads), device],
                                 cwd=engine, input=requests, text=True, encoding="utf-8", errors="replace",
                                 capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=180)
        elapsed = time.perf_counter() - started
        good = process.returncode == 0 and output1.is_file() and process.stdout.count('"status": "ready"') >= 2
        output1.unlink(missing_ok=True)
        # DirectML reports a numbered torch device (usually privateuseone:0),
        # while CPU is reported without an index.
        expected_device = '"device": "privateuseone' if device == "directml" else '"device": "cpu"'
        good = good and expected_device in process.stdout
        # A mode taking longer than this for one deliberately short phrase is
        # unsuitable for interactive replies even if it technically works.
        if good and elapsed <= 35.0 and (best is None or elapsed < best[0]): best = (elapsed, threads, device)
    benchmark.unlink(missing_ok=True)
    if best is None: raise RuntimeError("RVC не прошёл проверку ни на CPU, ни через DirectML")
    config = json.loads(config_path.read_text(encoding="utf-8-sig")) if config_path.exists() else {}
    config["rvc_cpu_threads"] = best[1]
    config["rvc_device"] = best[2]
    config["rvc_benchmark_seconds"] = round(best[0], 2)
    atomic_json(config_path, config)
    return best


def voice_store(request):
    operation = str(request.get("operation", "list"))
    if operation == "status":
        with _voice_lock:
            return dict(_voice_job)
    if operation == "installed":
        return {"voices": _installed_voices()}
    if operation == "list":
        path = _voice_path(request.get("path", ""))
        raw = _hf_voice_items(path)
        entries = []
        for item in raw:
            item_path = str(item.get("path", ""))
            entries.append({
                "name": item_path.rsplit("/", 1)[-1], "path": item_path,
                "type": item.get("type", ""), "size": int(item.get("size", 0) or 0),
                "sha256": str((item.get("lfs") or {}).get("oid", "")),
            })
        files = [entry for entry in entries if entry["type"] == "file"]
        return {"path": path, "entries": entries,
                "installable": any(x["name"].lower().endswith(".pth") for x in files),
                "installed": any(x.get("source_path") == path for x in _installed_voices())}
    if operation == "select":
        directory = Path(str(request.get("directory", ""))).resolve()
        store = (panel.BASE_DIR / "rvc_models" / "store").resolve()
        if store not in directory.parents:
            raise ValueError("Голос находится вне хранилища EFREN")
        metadata = json.loads((directory / "voice.json").read_text(encoding="utf-8"))
        model = directory / str(metadata["model"])
        index = directory / str(metadata.get("index", ""))
        if not model.is_file():
            raise ValueError("Файл модели не найден")
        config_path = panel.BASE_DIR / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8-sig")) if config_path.exists() else {}
        config.update({"rvc_enabled": True, "rvc_required": False,
                       "rvc_root": str(panel.BASE_DIR / "rvc_engine"),
                       "rvc_python": str(panel.BASE_DIR / "runtime" / "python" / "python.exe"),
                       "rvc_model": str(model), "rvc_index": str(index) if index.is_file() else "",
                       "rvc_timeout_seconds": 10})
        atomic_json(config_path, config)
        with _voice_lock:
            if _voice_job["running"]: raise ValueError("Дождитесь завершения текущей операции")
            _voice_job.update(running=True, message="Подготовка автоматической проверки RVC…", downloaded=0, total=0, error=False)
        def optimize():
            try:
                elapsed, threads, device = _optimize_rvc(model, index)
                label = "видеоядро / DirectML" if device == "directml" else f"CPU, {threads} потоков"
                with _voice_lock: _voice_job.update(running=False, downloaded=_voice_job["total"],
                    message=f"Голос выбран. Лучший режим: {label} ({elapsed:.1f} с на тест). Перезапустите помощника.", error=False)
            except Exception as exc:
                config = json.loads(config_path.read_text(encoding="utf-8-sig"))
                config["rvc_enabled"] = False; atomic_json(config_path, config)
                with _voice_lock: _voice_job.update(running=False, message="RVC отключён: " + str(exc), error=True)
        threading.Thread(target=optimize, name="RvcAutoBenchmark", daemon=True).start()
        return {"message": "Голос выбран. Сравниваю скорость CPU и видеоядра…", "optimizing": True}
    if operation == "delete":
        directory = Path(str(request.get("directory", ""))).resolve()
        store = (panel.BASE_DIR / "rvc_models" / "store").resolve()
        if store not in directory.parents or not (directory / "voice.json").is_file():
            raise ValueError("Это не установленный голос EFREN")
        config_path = panel.BASE_DIR / "config.json"
        try:
            config = json.loads(config_path.read_text(encoding="utf-8-sig"))
            active = Path(str(config.get("rvc_model", ""))).resolve()
            if directory in active.parents:
                config["rvc_enabled"] = False
                config["rvc_model"] = ""; config["rvc_index"] = ""
                atomic_json(config_path, config)
        except (OSError, ValueError, TypeError):
            pass
        shutil.rmtree(directory)
        return {"message": "Голос удалён."}
    if operation != "install":
        raise ValueError("Неизвестная операция магазина голосов")
    path = _voice_path(request.get("path", ""))
    with _voice_lock:
        if _voice_job["running"]:
            raise ValueError("Другой голос уже скачивается")
        _voice_job.update(running=True, message="Чтение состава голоса…", downloaded=0, total=0, error=False)

    def download():
        temporary = None
        try:
            items = [x for x in _hf_voice_items(path) if x.get("type") == "file"]
            models = [x for x in items if str(x.get("path", "")).lower().endswith(".pth")]
            indexes = [x for x in items if str(x.get("path", "")).lower().endswith(".index")]
            if not models:
                raise ValueError("В этой папке нет модели .pth")
            model = max(models, key=lambda x: int(x.get("size", 0) or 0))
            index = max(indexes, key=lambda x: int(x.get("size", 0) or 0)) if indexes else None
            chosen = [model] + ([index] if index else [])
            total = sum(int(x.get("size", 0) or 0) for x in chosen)
            if total <= 0 or total > 900 * 1024 * 1024:
                raise ValueError("Недопустимый размер голосового пакета")
            key = hashlib.sha256(path.encode("utf-8")).hexdigest()[:16]
            target = panel.BASE_DIR / "rvc_models" / "store" / key
            temporary = target.with_name(target.name + ".download")
            if temporary.exists(): shutil.rmtree(temporary)
            temporary.mkdir(parents=True)
            downloaded = 0
            with _voice_lock: _voice_job.update(total=total, message="Скачивание файлов голоса…")
            saved = []
            for remote in chosen:
                remote_path = str(remote["path"])
                name = Path(remote_path).name
                destination = temporary / name
                url = f"https://huggingface.co/{HF_VOICE_REPO}/resolve/main/{urllib.parse.quote(remote_path, safe='/')}?download=true"
                req = urllib.request.Request(url, headers={"User-Agent": "EFREN-Lite/0.1.5"})
                digest = hashlib.sha256()
                with urllib.request.urlopen(req, timeout=45) as response, destination.open("wb") as output:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk: break
                        output.write(chunk); digest.update(chunk); downloaded += len(chunk)
                        with _voice_lock: _voice_job["downloaded"] = downloaded
                expected = str((remote.get("lfs") or {}).get("oid", "")).lower()
                if expected and digest.hexdigest().lower() != expected:
                    raise ValueError("SHA-256 загруженного файла не совпал")
                saved.append(name)
            metadata = {"format": "EFREN-RVC-VOICE-1", "name": path.rsplit("/", 1)[-1],
                        "source_path": path, "repository": HF_VOICE_REPO,
                        "model": saved[0], "index": saved[1] if len(saved) > 1 else ""}
            atomic_json(temporary / "voice.json", metadata)
            if target.exists(): shutil.rmtree(target)
            os.replace(temporary, target); temporary = None
            with _voice_lock: _voice_job.update(running=False, message="Голос установлен.", downloaded=total, error=False)
        except Exception as exc:
            if temporary and temporary.exists(): shutil.rmtree(temporary, ignore_errors=True)
            with _voice_lock: _voice_job.update(running=False, message="Ошибка: " + str(exc), error=True)
    threading.Thread(target=download, name="VoiceStoreDownload", daemon=True).start()
    return {"message": "Скачивание начато."}


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
    if action == "voice_store": return voice_store(request)
    raise ValueError("Неизвестная функция")

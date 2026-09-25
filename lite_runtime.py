"""Per-installation Lite credentials and verified local process ownership."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import subprocess
import time


def installation_id(root):
    return hashlib.sha256(str(Path(root).resolve()).casefold().encode()).hexdigest()[:20]


def startup_file(root):
    return Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Startup" / ("EFREN_Lite_" + installation_id(root) + ".lnk")


def diagnostics(root):
    import psutil
    root = Path(root).resolve()
    memory = psutil.virtual_memory()
    process = owned_process(root)
    lines = ["Джарвис Lite: " + ("процесс запущен" if process else "выключен"),
             "Распознавание: локальная GigaAM v3 RNN-T / CPU",
             "Озвучка: Piper; RVC и общий Discord-бот не используются",
             f"Свободно ОЗУ: {memory.available / 1024**3:.1f} ГБ"]
    for name in ("runtime/python/python.exe", "models/gigaam/v3_rnnt.ckpt",
                 "runtime/piper/piper.exe", "tts_models/ru_RU-ruslan-medium.onnx",
                 "tts_models/ru_RU-ruslan-medium.onnx.json"):
        lines.append(("Есть: " if (root / name).is_file() else "ОТСУТСТВУЕТ: ") + name)
    return {"system": "\n".join(lines), "recognition": "Проверка наличия компонентов, не контрольных сумм. История распознавания — в журнале Джарвиса.\nЭта проверка не включает микрофон и не гарантирует слышимость звука."}


def authenticate(root, password):
    path = Path(root) / "lite-auth.json"
    if not isinstance(password, str) or len(password) > 256:
        raise ValueError("Недопустимый пароль")
    if not path.exists():
        if len(password) < 6:
            raise ValueError("Придумайте пароль длиной от 6 символов.")
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 300000).hex()
        try:
            with path.open("x", encoding="utf-8") as output:
                json.dump({"salt": salt.hex(), "hash": digest, "iterations": 300000}, output)
            return True
        except FileExistsError:
            pass
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("iterations") != 300000:
        raise ValueError("Повреждён файл пароля Lite; автоматический сброс запрещён.")
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(data["salt"]), 300000).hex()
    return hmac.compare_digest(actual, data["hash"])


def owned_process(root):
    import psutil
    root = Path(root).resolve()
    path = root / "runtime/lite-process.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        process = psutil.Process(int(data["pid"]))
        if abs(process.create_time() - float(data["created"])) > 0.01:
            return None
        expected = root / "runtime/python/python.exe"
        if Path(process.exe()).resolve() != expected:
            return None
        args = process.cmdline()
        if len(args) != 4 or args[1] != "-u" or Path(args[2]).resolve() != root / "main.py" or args[3] != "--resident":
            return None
        return process
    except (OSError, ValueError, KeyError, TypeError, psutil.Error):
        return None


def jarvis_action(root, operation):
    import psutil
    root = Path(root).resolve()
    if operation not in {"start", "stop", "restart"}:
        raise ValueError("Неизвестное действие")
    current = owned_process(root)
    record = root / "runtime/lite-process.json"
    if current is not None and operation in {"stop", "restart"}:
        # psutil checks PID reuse; never taskkill by unverified PID or process name.
        current.terminate()
        current.wait(timeout=8)
        record.unlink(missing_ok=True)
        current = None
    if operation in {"start", "restart"} and current is None:
        for name in ("runtime/python/python.exe", "main.py", "models/gigaam/v3_rnnt.ckpt",
                     "runtime/piper/piper.exe", "tts_models/ru_RU-ruslan-medium.onnx"):
            if not (root / name).is_file():
                raise FileNotFoundError("Не хватает файла Lite: " + name)
        environment = os.environ.copy()
        for key in ("PYTHONHOME", "PYTHONPATH"):
            environment.pop(key, None)
        environment.update(PYTHONNOUSERSITE="1", PYTHONIOENCODING="utf-8")
        logs = root / "logs"
        logs.mkdir(exist_ok=True)
        with (logs / "lite-process.log").open("ab") as log:
            process = subprocess.Popen([str(root / "runtime/python/python.exe"), "-u",
                                        str(root / "main.py"), "--resident"], cwd=root,
                                       env=environment, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            created = psutil.Process(process.pid).create_time()
            record.parent.mkdir(exist_ok=True)
            record.write_text(json.dumps({"pid": process.pid, "created": created}), encoding="utf-8")
        except Exception:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=8)
            raise
        time.sleep(0.2)
        if process.poll() is not None:
            record.unlink(missing_ok=True)
            raise RuntimeError("Джарвис завершился при запуске. Подробности: logs/lite-process.log")
        return "Процесс запущен; голосовая модель загружается."
    return "Готово"

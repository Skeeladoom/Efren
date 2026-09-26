# JARVIS-MAIN-v0.9.1-JARVIS-WORD-VARIANTS

import argparse
from assistant_identity import wake_aliases, names as assistant_names, display_names
import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from discord_tools import execute_discord_voice_command
from lite_policy import is_lite, enforce_settings
from memory import Memory
from router import LocalRouter, Route
from tools import WindowsTools
from tts import LocalTTS
from voice import VoiceListener, VoiceUnavailable


MAIN_CODE_VERSION = "JARVIS-MAIN-v0.9.1-JARVIS-WORD-VARIANTS"

BROWSER_LABELS = {
    "opera_gx": "Opera GX",
    "chrome": "Google Chrome",
    "edge": "Microsoft Edge",
    "firefox": "Mozilla Firefox",
    "brave": "Brave",
    "vivaldi": "Vivaldi",
    "yandex": "Яндекс Браузер",
    "chromium": "Chromium",
}

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
SETTINGS_PATH = BASE_DIR / "jarvis_settings.json"
JARVIS_PID_FILE = BASE_DIR / "jarvis.pid"
JARVIS_MUTEX_NAME = "Local\\JARVIS_ASSISTANT_SINGLE_INSTANCE"
if is_lite(BASE_DIR):
    from lite_runtime import installation_id
    JARVIS_MUTEX_NAME = "Local\\EFREN.Lite.Jarvis." + installation_id(BASE_DIR)
    JARVIS_PID_FILE = BASE_DIR / "lite-jarvis.pid"


DEFAULT_RUNTIME_SETTINGS = {
    "voice_enabled": True,
    "tts_enabled": True,
    "discord_commands_enabled": True,
    "windows_commands_enabled": True,
    "default_browser": "opera_gx",
    "browser_clarification_enabled": True,

    # explicit  = только "спроси Квена..."
    # fallback  = неизвестные команды автоматически -> Qwen
    # disabled  = Qwen полностью выключен
    "qwen_mode": "explicit",

    # Пока зарезервировано для будущего Discord STT.
    "friends_voice_enabled": False,
    "friends_can_use_windows": False,
    "friends_can_use_discord": False,
    "friends_can_use_qwen": False,
}


WINDOWS_ROUTE_KINDS = {
    "macro_phrase",
    "macro_close",
    "open_app",
    "close_app",
    "get_active_window",
    "minimize_window",
    "maximize_window",
    "restore_window",
    "focus_window",
    "close_window",
    "list_windows",
    "click_ui_element",
    "click_colored_button",
    "dota_match_search",
    "apple_game_start",
    "apple_game_stop",
    "press_key",
    "type_text",
    "browser_search",
    "open_url",
    "browser_request",
    "browser_default",
    "open_system",
    "open_folder",
    "screenshot",
    "volume",
    "time",
    "computer_shutdown",
    "computer_restart",
}


DISCORD_ROUTE_KINDS = {
    "discord_bot_start",
    "discord_bot_stop",
    "discord_bot_restart",
    "discord_bot_status",
    "discord_voice",
}


# =============================================================
# DISCORD BOT
# =============================================================

DISCORD_BOT_DIR = Path(
    r"C:\DiscordBot"
)

DISCORD_BOT_FILE = (
    DISCORD_BOT_DIR
    / "index.js"
)

DISCORD_BOT_PID_FILE = (
    BASE_DIR
    / "discord_bot.pid"
)

DISCORD_BOT_HEALTH_URL = (
    "http://127.0.0.1:8765/health"
)

NVM_NODE = Path(
    r"C:\Users\Skeeladoom\AppData\Local\nvm\v18.20.4\node.exe"
)


HELP = """Команды JARVIS:
- открыть/закрыть приложение;
- открыть Доту;
- открыть Steam-игры и приложения: Soundpad, Lossless Scaling, Counter-Strike 2;
- открыть Chrome, Opera GX или Microsoft Edge;
- выбрать основной браузер или уточнять его голосом;
- открыть настройки Windows, панель управления и диспетчеры;
- открыть Загрузки, Документы, Рабочий стол и другие папки;
- свернуть, восстановить, развернуть или закрыть окно;
- узнать активное окно;
- переключиться на Discord, Steam, Dota 2, VS Code;
- открыть Telegram/AyuGram и библиотеку Steam;
- перечислить открытые окна и нажать доступный элемент активного окна по названию;
- найти зелёную/синюю кнопку внутри активного окна;
- начать поиск игры в Dota 2 двумя визуально проверяемыми нажатиями;
- играть в локальную игру с яблоками, пропуская жёлтые звёзды; остановка — F8;
- нажимать основные клавиши, вводить текст и искать через адресную строку Chrome;
- сделать скриншот;
- изменить громкость;
- сказать время;
- повторить произвольную фразу командами «скажи», «повтори», «произнеси» или «озвучь»;
- включить/выключить/перезапустить Пятницу (Discord-бота);
- проверить статус Пятницы;
- выполнять Discord voice-команды;
- отвечать через локальный Qwen;
- показать этот список командами «помощь», «help» или «покажи список возможностей»;
- настройки Control Panel применяются без перезапуска.

Qwen:
- explicit — только «спроси Квена ...»;
- fallback — неизвестные запросы автоматически идут в Qwen;
- disabled — Qwen полностью отключён.

Режимы:
python main.py
python main.py --resident
python main.py --voice
python main.py --chat
python main.py --text
python main.py --install-startup
python main.py --remove-startup
"""


class JarvisInstanceGuard:
    """Не позволяет запустить два resident-экземпляра JARVIS."""

    ERROR_ALREADY_EXISTS = 183

    def __init__(self):
        self.handle = None

    def acquire(self):
        if os.name != "nt":
            JARVIS_PID_FILE.write_text(
                str(os.getpid()),
                encoding="utf-8",
            )
            return True

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateMutexW(
            None,
            False,
            JARVIS_MUTEX_NAME,
        )

        if not handle:
            return False

        if kernel32.GetLastError() == self.ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(
                handle
            )
            return False

        self.handle = handle
        JARVIS_PID_FILE.write_text(
            str(os.getpid()),
            encoding="utf-8",
        )

        return True

    def release(self):
        try:
            if JARVIS_PID_FILE.exists():
                saved = JARVIS_PID_FILE.read_text(
                    encoding="utf-8"
                ).strip()

                if saved == str(os.getpid()):
                    JARVIS_PID_FILE.unlink()

        except OSError:
            pass

        if self.handle and os.name == "nt":
            ctypes.windll.kernel32.CloseHandle(
                self.handle
            )
            self.handle = None


# =============================================================
# DISCORD BOT MANAGER
# =============================================================


class DiscordBotManager:
    def __init__(self):
        self.bot_dir = (
            DISCORD_BOT_DIR
        )

        self.bot_file = (
            DISCORD_BOT_FILE
        )

        self.pid_file = (
            DISCORD_BOT_PID_FILE
        )

        self.health_url = (
            DISCORD_BOT_HEALTH_URL
        )

    # ---------------------------------------------------------
    # HEALTH
    # ---------------------------------------------------------

    def is_online(self):
        try:
            request = (
                urllib.request.Request(
                    self.health_url,
                    method="GET",
                )
            )

            with urllib.request.urlopen(
                request,
                timeout=1.0,
            ) as response:
                return (
                    200
                    <= response.status
                    < 300
                )

        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            TimeoutError,
            OSError,
        ):
            return False

    # ---------------------------------------------------------
    # PID
    # ---------------------------------------------------------

    def _save_pid(
        self,
        pid,
    ):
        self.pid_file.write_text(
            str(
                int(pid)
            ),
            encoding="utf-8",
        )

    def _read_pid(self):
        if not self.pid_file.exists():
            return None

        try:
            text = (
                self.pid_file
                .read_text(
                    encoding="utf-8"
                )
                .strip()
            )

            if not text:
                return None

            return int(
                text
            )

        except (
            OSError,
            ValueError,
        ):
            return None

    def _delete_pid_file(self):
        try:
            if self.pid_file.exists():
                self.pid_file.unlink()

        except OSError:
            pass

    # ---------------------------------------------------------
    # PROCESS CHECK
    # ---------------------------------------------------------

    def _process_matches_bot(
        self,
        pid,
    ):
        """
        Подтверждает не только существование PID, но и то,
        что это node.exe, запущенный именно с index.js бота.

        При любой неоднозначности возвращает False: чужой
        процесс безопаснее не остановить, чем завершить.
        """

        if not pid:
            return False

        try:
            pid = int(pid)

            powershell = (
                shutil.which("powershell.exe")
                or shutil.which("powershell")
            )

            if not powershell:
                return False

            script = (
                "$process = Get-CimInstance Win32_Process "
                f"-Filter 'ProcessId = {pid}' "
                "-ErrorAction SilentlyContinue; "
                "if ($null -ne $process) { "
                "$process | Select-Object "
                "ProcessId, ExecutablePath, CommandLine "
                "| ConvertTo-Json -Compress }"
            )

            result = subprocess.run(
                [
                    powershell,
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    script,
                ],
                capture_output=True,
                text=True,
                timeout=3.0,
                creationflags=(
                    subprocess.CREATE_NO_WINDOW
                    if os.name == "nt"
                    else 0
                ),
            )

            if result.returncode != 0:
                return False

            raw = (
                result.stdout
                or ""
            ).strip()

            if not raw:
                return False

            info = json.loads(raw)

            if int(
                info.get(
                    "ProcessId",
                    0,
                )
            ) != pid:
                return False

            executable = str(
                info.get(
                    "ExecutablePath",
                    "",
                )
                or ""
            ).strip()

            command_line = str(
                info.get(
                    "CommandLine",
                    "",
                )
                or ""
            ).strip()

            if not executable or not command_line:
                return False

            if (
                Path(executable).name.lower()
                != "node.exe"
            ):
                return False

            expected_script = os.path.normcase(
                str(
                    self.bot_file.resolve()
                )
            )

            command_arguments = [
                os.path.normcase(
                    token.strip().strip('"')
                )
                for token in re.findall(
                    r'"[^"]*"|\S+',
                    command_line,
                )
            ]

            return (
                expected_script
                in command_arguments
            )

        except (
            OSError,
            ValueError,
            TypeError,
            json.JSONDecodeError,
            subprocess.SubprocessError,
        ):
            return False

    # ---------------------------------------------------------
    # NODE
    # ---------------------------------------------------------

    @staticmethod
    def _find_node():
        if NVM_NODE.exists():
            return str(
                NVM_NODE
            )

        node = shutil.which(
            "node.exe"
        )

        if node:
            return node

        node = shutil.which(
            "node"
        )

        if node:
            return node

        candidates = (
            Path(
                r"C:\Program Files\nodejs\node.exe"
            ),
            Path(
                r"C:\Program Files (x86)\nodejs\node.exe"
            ),
            Path(
                os.path.expandvars(
                    r"%LOCALAPPDATA%\Programs\nodejs\node.exe"
                )
            ),
        )

        for candidate in candidates:
            if candidate.exists():
                return str(
                    candidate
                )

        return None

    # ---------------------------------------------------------
    # START
    # ---------------------------------------------------------

    def start(self):
        if self.is_online():
            return (
                "Пятница уже включена."
            )

        if not self.bot_file.exists():
            return (
                "Не найден файл Пятницы: "
                f"{self.bot_file}"
            )

        node = (
            self._find_node()
        )

        if not node:
            return (
                "Не найден Node.js."
            )

        old_pid = (
            self._read_pid()
        )

        if (
            old_pid
            and self._process_matches_bot(
                old_pid
            )
        ):
            return (
                "Процесс Пятницы уже запущен, "
                "но локальный bridge пока не отвечает."
            )

        self._delete_pid_file()

        creationflags = 0
        startupinfo = None

        if os.name == "nt":
            creationflags = (
                subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.CREATE_NO_WINDOW
            )

            startupinfo = (
                subprocess.STARTUPINFO()
            )

            startupinfo.dwFlags |= (
                subprocess.STARTF_USESHOWWINDOW
            )

            startupinfo.wShowWindow = 0

        try:
            bot_env = os.environ.copy()
            bot_env["FRIDAY_PROJECT_DIR"] = str(BASE_DIR)
            worker_python = Path(sys.executable).with_name("python.exe")
            bot_env["FRIDAY_PYTHON_EXE"] = str(
                worker_python if worker_python.exists() else sys.executable
            )

            process = subprocess.Popen(
                [
                    node,
                    str(
                        self.bot_file
                    ),
                ],
                cwd=str(
                    self.bot_dir
                ),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
                startupinfo=startupinfo,
                env=bot_env,
            )

        except Exception as exc:
            return (
                "Не удалось запустить "
                "Пятницу: "
                f"{exc}"
            )

        self._save_pid(
            process.pid
        )

        deadline = (
            time.monotonic()
            + 8.0
        )

        while (
            time.monotonic()
            < deadline
        ):
            if self.is_online():
                return (
                    "Пятница включена."
                )

            if (
                process.poll()
                is not None
            ):
                self._delete_pid_file()

                return (
                    "Пятница запустилась, "
                    "но сразу завершилась."
                )

            time.sleep(
                0.25
            )

        if (
            process.poll()
            is None
        ):
            return (
                "Пятница запущена. "
                "Подключение к Discord ещё может занять "
                "несколько секунд."
            )

        self._delete_pid_file()

        return (
            "Не удалось запустить Пятницу."
        )

    # ---------------------------------------------------------
    # STOP
    # ---------------------------------------------------------

    def stop(self):
        pid = (
            self._read_pid()
        )

        if pid:
            if not self._process_matches_bot(
                pid
            ):
                self._delete_pid_file()

                if self.is_online():
                    return (
                        "Пятница работает, "
                        "но сохранённый PID уже неактуален. "
                        "Я не буду завершать все процессы Node.js."
                    )

                return (
                    "Пятница уже выключена."
                )

            try:
                result = subprocess.run(
                    [
                        "taskkill",
                        "/PID",
                        str(pid),
                        "/T",
                        "/F",
                    ],
                    capture_output=True,
                    text=True,
                    creationflags=(
                        subprocess.CREATE_NO_WINDOW
                        if os.name == "nt"
                        else 0
                    ),
                )

            except Exception as exc:
                return (
                    "Не удалось выключить "
                    "Пятницу: "
                    f"{exc}"
                )

            if result.returncode != 0:
                return (
                    "Пятницу не удалось "
                    "нормально выключить."
                )

            self._delete_pid_file()

            time.sleep(
                0.4
            )

            if self.is_online():
                return (
                    "Процесс Пятницы был остановлен, "
                    "но bridge всё ещё отвечает."
                )

            return (
                "Пятница выключена."
            )

        if self.is_online():
            return (
                "Пятница работает, но была запущена "
                "не через JARVIS. Я не буду убивать все "
                "процессы Node.js."
            )

        return (
            "Пятница уже выключена."
        )

    # ---------------------------------------------------------
    # RESTART
    # ---------------------------------------------------------

    def restart(self):
        pid = (
            self._read_pid()
        )

        if pid:
            stop_result = (
                self.stop()
            )

            time.sleep(
                0.6
            )

            start_result = (
                self.start()
            )

            if (
                "Пятница включена."
                in start_result
            ):
                return (
                    "Пятница перезапущена."
                )

            return (
                f"{stop_result} "
                f"{start_result}"
            )

        if self.is_online():
            return (
                "Пятница уже работает, "
                "но запущена не через JARVIS. "
                "Безопасный перезапуск недоступен."
            )

        return (
            self.start()
        )

    # ---------------------------------------------------------
    # STATUS
    # ---------------------------------------------------------

    def status(self):
        if self.is_online():
            return (
                "Пятница включена."
            )

        pid = (
            self._read_pid()
        )

        if (
            pid
            and self._process_matches_bot(
                pid
            )
        ):
            return (
                "Процесс Пятницы запущен, "
                "но bridge не отвечает."
            )

        return (
            "Пятница выключена."
        )


# =============================================================
# JARVIS
# =============================================================


class Jarvis:
    def __init__(self):
        self.config = json.loads(
            CONFIG_PATH.read_text(
                encoding="utf-8"
            )
        )

        self.tools = WindowsTools(
            self.config,
            BASE_DIR,
        )

        self.router = LocalRouter(
            self.config.get(
                "wake_words",
                ["джарвис"],
            ),
            self.tools,
        )

        self.memory = Memory(
            BASE_DIR / "memory.json",
            self.config.get(
                "context_messages",
                8,
            ),
        )

        self.llm = None
        if not is_lite(BASE_DIR):
            from local_llm import LocalLLM
            self.llm = LocalLLM(
                self.config,
                self.tools,
                windows_allowed=(
                    lambda: bool(
                        self.refresh_runtime_settings().get(
                            "windows_commands_enabled",
                            True,
                        )
                    )
                ),
            )

        self.tts = LocalTTS(
            self.config,
        )

        self.discord_bot = (
            DiscordBotManager()
        )

        self.runtime_settings = (
            self._load_runtime_settings()
        )

        self.pending_browser_until = 0.0

    # =========================================================
    # CONTROL PANEL SETTINGS
    # =========================================================

    def _load_runtime_settings(
        self,
    ):
        settings = (
            DEFAULT_RUNTIME_SETTINGS.copy()
        )

        if not SETTINGS_PATH.exists():
            return enforce_settings(settings, is_lite(BASE_DIR))

        try:
            loaded = json.loads(
                SETTINGS_PATH.read_text(
                    encoding="utf-8"
                )
            )

            if isinstance(
                loaded,
                dict,
            ):
                settings.update(
                    loaded
                )

        except (
            OSError,
            ValueError,
            TypeError,
        ):
            pass

        mode = str(
            settings.get(
                "qwen_mode",
                "explicit",
            )
        ).lower().strip()

        if mode not in {
            "explicit",
            "fallback",
            "disabled",
        }:
            mode = (
                "explicit"
            )

        settings[
            "qwen_mode"
        ] = mode

        browser = str(
            settings.get(
                "default_browser",
                "opera_gx",
            )
        ).lower().strip()

        configured_apps = self.config.get("apps", {})
        if browser not in BROWSER_LABELS or browser not in configured_apps:
            browser = next(
                (key for key in BROWSER_LABELS if key in configured_apps),
                "edge",
            )

        settings[
            "default_browser"
        ] = browser

        settings[
            "browser_clarification_enabled"
        ] = bool(
            settings.get(
                "browser_clarification_enabled",
                True,
            )
        )

        return enforce_settings(settings, is_lite(BASE_DIR))

    def refresh_runtime_settings(
        self,
    ):
        self.runtime_settings = (
            self._load_runtime_settings()
        )

        return (
            self.runtime_settings
        )

    def voice_enabled(
        self,
    ):
        settings = (
            self.refresh_runtime_settings()
        )

        return bool(
            settings.get(
                "voice_enabled",
                True,
            )
        )

    def tts_enabled(
        self,
    ):
        settings = (
            self.refresh_runtime_settings()
        )

        return bool(
            settings.get(
                "tts_enabled",
                True,
            )
        )

    # =========================================================
    # TEXT NORMALIZATION
    # =========================================================

    @staticmethod
    def _normalize_text(
        text,
    ):
        text = (
            str(text or "")
            .lower()
            .replace(
                "ё",
                "е",
            )
        )

        text = re.sub(
            r"[^а-яa-z0-9 ]+",
            " ",
            text,
        )

        return " ".join(
            text.split()
        )

    # =========================================================
    # EASTER EGG
    # =========================================================

    def _is_easter_egg(
        self,
        text,
    ):
        t = (
            self._normalize_text(
                text
            )
        )

        wake_words = (
            "джарвис",
            "джарви",
            "жарвис",
            "жарви",
            "джервис",
            "джерви",
            "жервис",
            "жерви",
            "джавис",
            "жавис",
            "джарвес",
            "жарвес",
            "джар вис",
            "жар вис",
        )

        has_wake = any(
            (
                t == wake
                or t.startswith(
                    wake + " "
                )
                or t.endswith(
                    " " + wake
                )
                or (
                    " " + wake + " "
                    in " " + t + " "
                )
            )
            for wake
            in wake_aliases("jarvis", wake_words)
        )

        if not has_wake:
            return False

        return (
            "че за хуйня"
            in t
            or
            "что за хуйня"
            in t
        )

    # =========================================================
    # MAIN REQUEST HANDLER
    # =========================================================

    def handle(
        self,
        text,
    ):
        settings = (
            self.refresh_runtime_settings()
        )

        if self._is_easter_egg(
            text
        ):
            return (
                "answer",
                "Сэр, я сам в ахуе.",
            )

        route = None
        now = time.monotonic()

        if self.pending_browser_until:
            if now > self.pending_browser_until:
                self.pending_browser_until = 0.0

            else:
                normalized = self._normalize_text(
                    text
                )

                if any(
                    word in normalized
                    for word in (
                        "отмена",
                        "отмени",
                        "не надо",
                    )
                ):
                    self.pending_browser_until = 0.0

                    return (
                        "answer",
                        "Отменил выбор браузера.",
                    )

                browser = self.router.browser_from_text(
                    text
                )

                if browser:
                    self.pending_browser_until = 0.0
                    route = Route(
                        "open_app",
                        {
                            "app": browser,
                        },
                    )

        if route is None:
            route = self.router.route(
                text
            )

        if (
            route.kind
            == "empty"
        ):
            return (
                "empty",
                "",
            )

        if (
            route.kind
            == "sleep"
        ):
            return (
                "sleep",
                "Отключаюсь.",
            )

        if (
            route.kind
            == "exit"
        ):
            return (
                "exit",
                "Завершаю работу.",
            )

        if (
            route.kind
            == "help"
        ):
            return (
                "answer",
                HELP,
            )

        qwen_mode = (
            settings.get(
                "qwen_mode",
                "explicit",
            )
        )

        # =====================================================
        # "СПРОСИ КВЕНА" БЕЗ ВОПРОСА
        # =====================================================

        if (
            route.kind
            == "qwen_empty"
        ):
            if (
                qwen_mode
                == "disabled"
            ):
                return (
                    "answer",
                    "Qwen отключён в панели управления.",
                )

            return (
                "answer",
                "Что спросить у Квена?",
            )

        # =====================================================
        # UNKNOWN
        # =====================================================

        if (
            route.kind
            == "unknown"
        ):
            # explicit:
            # неизвестный шум Vosk
            # просто игнорируется.
            #
            # disabled:
            # то же самое.
            if (
                qwen_mode
                != "fallback"
            ):
                return (
                    "empty",
                    "",
                )

            # fallback:
            # старое поведение.
            route.kind = (
                "llm"
            )

            route.args = {
                "text":
                    route.args.get(
                        "text",
                        text,
                    )
            }

        # =====================================================
        # QWEN PERMISSION
        # =====================================================

        if (
            route.kind
            == "llm"
            and
            qwen_mode
            == "disabled"
        ):
            return (
                "answer",
                "Qwen отключён в панели управления.",
            )

        # =====================================================
        # DISCORD PERMISSION
        # =====================================================

        if (
            route.kind
            in DISCORD_ROUTE_KINDS
            and not bool(
                settings.get(
                    "discord_commands_enabled",
                    True,
                )
            )
        ):
            return (
                "answer",
                "Discord-команды отключены в панели управления.",
            )

        # =====================================================
        # WINDOWS PERMISSION
        # =====================================================

        if (
            route.kind
            in WINDOWS_ROUTE_KINDS
            and not bool(
                settings.get(
                    "windows_commands_enabled",
                    True,
                )
            )
        ):
            return (
                "answer",
                "Windows-команды отключены в панели управления.",
            )

        # =====================================================
        # BROWSER CHOICE
        # =====================================================

        if route.kind == "browser_default":
            route = Route(
                "open_app",
                {
                    "app": settings.get(
                        "default_browser",
                        "opera_gx",
                    ),
                },
            )

        if route.kind == "browser_request":
            if bool(
                settings.get(
                    "browser_clarification_enabled",
                    True,
                )
            ):
                self.pending_browser_until = (
                    time.monotonic()
                    + 15.0
                )

                available = [
                    label
                    for key, label in BROWSER_LABELS.items()
                    if key in self.config.get("apps", {})
                ]
                return (
                    "answer",
                    "Какой браузер открыть: " + ", ".join(available) + "? "
                    "Назовите его вместе со словом «Джарвис».",
                )

            route = Route(
                "open_app",
                {
                    "app": settings.get(
                        "default_browser",
                        "opera_gx",
                    ),
                },
            )

        self.memory.add(
            "user",
            text,
        )

        try:
            answer = (
                self._execute_route(
                    route
                )
            )

        except Exception as exc:
            answer = (
                f"Ошибка: {exc}"
            )

        if answer is None:
            answer = ""

        answer = str(
            answer
        )

        if answer:
            self.memory.add(
                "assistant",
                answer,
            )

        return (
            "answer",
            answer,
        )

    # =========================================================
    # ROUTE EXECUTION
    # =========================================================

    def _execute_route(
        self,
        route,
    ):
        kind = (
            route.kind
        )

        args = (
            route.args
        )

        if is_lite(BASE_DIR) and (kind in DISCORD_ROUTE_KINDS or kind == "llm"):
            return "Эта команда недоступна в Джарвис Lite."

        # =====================================================
        # DISCORD BOT
        # =====================================================

        if kind == "discord_bot_start":
            return (
                self.discord_bot
                .start()
            )

        if kind == "discord_bot_stop":
            return (
                self.discord_bot
                .stop()
            )

        if kind == "discord_bot_restart":
            return (
                self.discord_bot
                .restart()
            )

        if kind == "discord_bot_status":
            return (
                self.discord_bot
                .status()
            )

        # =====================================================
        # DISCORD VOICE
        # =====================================================

        if kind == "discord_voice":
            return (
                execute_discord_voice_command(
                    args["text"]
                )
            )

        # =====================================================
        # APPLICATIONS
        # =====================================================

        if kind == "say":
            return str(args.get("text", "")).strip()

        if kind == "macro_phrase":
            runner = BASE_DIR / "macro_runner.py"
            scenario = Path(args.get("path", ""))
            if not runner.is_file() or not scenario.is_file():
                return "Сценарий не найден. Открой конструктор и сохрани его заново."
            pythonw = Path(sys.executable).with_name("pythonw.exe")
            executable = pythonw if pythonw.is_file() else Path(sys.executable)
            subprocess.Popen(
                [str(executable), str(runner), "--run", str(scenario)],
                cwd=str(BASE_DIR),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return f"Запускаю сценарий «{scenario.stem}»."

        if kind == "macro_close":
            runner = BASE_DIR / "macro_runner.py"
            scenario = Path(args.get("path", ""))
            if not runner.is_file() or not scenario.is_file():
                return "Сценарий не найден."
            pythonw = Path(sys.executable).with_name("pythonw.exe")
            executable = pythonw if pythonw.is_file() else Path(sys.executable)
            subprocess.Popen([str(executable), str(runner), "--close", str(scenario)],
                             cwd=str(BASE_DIR), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return f"Закрываю приложение из сценария «{scenario.stem}»."

        if kind == "open_app":
            return (
                self.tools.open_app(
                    args["app"]
                )
            )

        if kind == "close_app":
            return (
                self.tools.close_app(
                    args["app"]
                )
            )

        if kind == "open_system":
            return (
                self.tools.open_system_item(
                    args["target"]
                )
            )

        if kind == "open_folder":
            return (
                self.tools.open_folder(
                    args["target"]
                )
            )

        # =====================================================
        # WINDOWS
        # =====================================================

        if kind == "get_active_window":
            return (
                self.tools
                .get_active_window()
            )

        if kind == "minimize_window":
            return (
                self.tools
                .minimize_window(
                    args.get(
                        "target",
                        "active",
                    )
                )
            )

        if kind == "maximize_window":
            return (
                self.tools
                .maximize_window(
                    args.get(
                        "target",
                        "active",
                    )
                )
            )

        if kind == "restore_window":
            return (
                self.tools
                .restore_window(
                    args.get(
                        "target",
                        "active",
                    )
                )
            )

        if kind == "focus_window":
            return (
                self.tools
                .focus_window(
                    args["target"]
                )
            )

        if kind == "close_window":
            return (
                self.tools
                .close_window(
                    args.get(
                        "target",
                        "active",
                    )
                )
            )

        if kind == "list_windows":
            return self.tools.list_windows()

        if kind == "click_ui_element":
            return self.tools.click_ui_element(
                args.get("label", "")
            )

        if kind == "click_colored_button":
            return self.tools.click_colored_button(
                color=args.get("color", "green"),
                target=args.get("target", "active"),
            )

        if kind == "dota_match_search":
            return self.tools.start_dota_match_search()

        if kind == "apple_game_start":
            return self.tools.start_apple_game_bot()

        if kind == "apple_game_stop":
            return self.tools.stop_apple_game_bot()

        if kind == "press_key":
            return self.tools.press_key(args.get("key", ""))

        if kind == "type_text":
            return self.tools.type_text(args.get("text", ""))

        if kind == "browser_search":
            return self.tools.browser_search(
                args.get("query", ""),
                args.get("browser", "chrome"),
            )

        # =====================================================
        # WEB
        # =====================================================

        if kind == "open_url":
            return (
                self.tools.open_url(
                    args["url"]
                )
            )

        # =====================================================
        # SCREENSHOT
        # =====================================================

        if kind == "screenshot":
            return (
                self.tools
                .take_screenshot()
            )

        # =====================================================
        # VOLUME
        # =====================================================

        if kind == "volume":
            return (
                self.tools
                .set_volume(
                    args["value"]
                )
            )

        # =====================================================
        # TIME
        # =====================================================

        if kind == "time":
            return (
                self.tools
                .get_time()
            )

        if kind == "computer_shutdown":
            return self.tools.computer_power(restart=False)

        if kind == "computer_restart":
            return self.tools.computer_power(restart=True)

        # =====================================================
        # QWEN
        # =====================================================

        if kind == "llm":
            if self.llm is None:
                return "Qwen недоступен в Джарвис Lite."
            history = (
                self.memory
                .recent()[:-1]
            )

            return (
                self.llm.chat(
                    args["text"],
                    history,
                )
            )

        return (
            "Неизвестный маршрут: "
            f"{kind}"
        )


# =============================================================
# OUTPUT
# =============================================================


def print_answer(
    answer,
):
    if answer:
        print(
            assistant_names()["jarvis"] + ":",
            answer,
        )


def speak_answer(
    jarvis,
    answer,
):
    if not answer:
        return

    # Перечитывается jarvis_settings.json,
    # поэтому выключение TTS применяется
    # без перезапуска JARVIS.
    if not jarvis.tts_enabled():
        return

    jarvis.tts.say(
        answer
    )


# =============================================================
# KEYBOARD MODE
# =============================================================


def keyboard_mode(
    jarvis,
    speak,
):
    mode_name = (
        "CHAT"
        if speak
        else "TEXT"
    )

    print(
        f"{MAIN_CODE_VERSION} "
        f"— {mode_name}"
    )

    print(
        "Ctrl+C — выход.\n"
    )

    try:
        while True:
            try:
                text = input(
                    "YOU: "
                ).strip()

            except (
                EOFError,
                KeyboardInterrupt,
            ):
                break

            if not text:
                continue

            state, answer = (
                jarvis.handle(
                    text
                )
            )

            if (
                state
                == "empty"
            ):
                continue

            print_answer(
                answer
            )

            if speak:
                speak_answer(
                    jarvis,
                    answer,
                )

            if (
                state
                == "exit"
            ):
                break

            if (
                state
                == "sleep"
            ):
                continue

    finally:
        jarvis.tts.stop()


# =============================================================
# VOICE / RESIDENT
# =============================================================


def voice_mode(
    jarvis,
    resident=False,
):
    try:
        listener = (
            VoiceListener(
                jarvis.config,
                jarvis.config.get(
                    "wake_words",
                    ["джарвис"],
                ),
            )
        )

    except VoiceUnavailable as exc:
        print(
            "VOICE ERROR:",
            exc,
        )

        jarvis.tts.stop()

        return 1

    if is_lite(BASE_DIR):
        ready = BASE_DIR / "runtime/lite-ready.json"
        temporary = ready.with_suffix(".tmp")
        temporary.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
        os.replace(temporary, ready)

    if not resident:
        print(
            f"{MAIN_CODE_VERSION} "
            "— VOICE"
        )

    print(
        "[JARVIS] Ожидание "
        "wake-word «Джарвис»."
    )

    # =========================================================
    # WAKE
    # =========================================================

    def on_wake():
        # VoiceListener продолжает существовать,
        # но при выключенном тумблере
        # JARVIS полностью игнорирует голос.
        if not jarvis.voice_enabled():
            return

        listener.wake()

        print_answer(
            "Слушаю."
        )

        speak_answer(
            jarvis,
            "Слушаю.",
        )

    # =========================================================
    # VOICE COMMAND
    # =========================================================

    def on_text(
        text,
    ):
        if not jarvis.voice_enabled():
            listener._write_log(
                "blocked",
                text=text,
                accepted=False,
                error="Голосовые команды JARVIS выключены в панели управления.",
            )
            return

        state, answer = (
            jarvis.handle(
                text
            )
        )

        listener._write_log(
            "result",
            text=text,
            accepted=(state != "empty"),
            result=answer,
            command_state=state,
        )

        if (
            state
            == "empty"
        ):
            return

        print_answer(
            answer
        )

        speak_answer(
            jarvis,
            answer,
        )

        if (
            state
            == "sleep"
        ):
            listener.sleep()
            return

        if (
            state
            == "exit"
        ):
            listener.request_stop()
            return

    try:
        listener.listen_forever(
            on_text,
            on_wake,
        )

    except VoiceUnavailable as exc:
        print(
            "VOICE ERROR:",
            exc,
        )

        return 1

    except KeyboardInterrupt:
        print(
            "\nJARVIS: Остановлен."
        )

    finally:
        jarvis.tts.stop()

    return 0


# =============================================================
# STARTUP
# =============================================================


def startup_dir():
    appdata = (
        os.environ.get(
            "APPDATA"
        )
    )

    if not appdata:
        raise RuntimeError(
            "Не найден APPDATA."
        )

    return (
        Path(appdata)
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / "Startup"
    )


def startup_file():
    return (
        startup_dir()
        / "JARVIS.cmd"
    )


def pythonw_path():
    current = Path(
        sys.executable
    )

    candidate = (
        current.parent
        / "pythonw.exe"
    )

    if candidate.exists():
        return candidate

    found = shutil.which(
        "pythonw.exe"
    )

    if found:
        return Path(
            found
        )

    return current


def install_startup():
    folder = (
        startup_dir()
    )

    folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    cmd_path = (
        startup_file()
    )

    py = (
        pythonw_path()
    )

    main_py = (
        BASE_DIR
        / "main.py"
    )

    content = (
        "@echo off\n"
        f'cd /d "{BASE_DIR}"\n'
        f'start "" /min "{py}" '
        f'"{main_py}" --resident\n'
    )

    cmd_path.write_text(
        content,
        encoding="utf-8",
    )

    print(
        "JARVIS добавлен "
        "в автозапуск:"
    )

    print(
        cmd_path
    )

    print(
        "\nПри следующем входе "
        "в Windows wake-listener "
        "запустится автоматически."
    )


def remove_startup():
    path = (
        startup_file()
    )

    if path.exists():
        path.unlink()

        print(
            "JARVIS удалён "
            "из автозапуска."
        )

    else:
        print(
            "JARVIS не найден "
            "в автозапуске."
        )


# =============================================================
# ARGUMENTS
# =============================================================


def build_parser():
    parser = (
        argparse.ArgumentParser(
            description=(
                "JARVIS local "
                "Windows assistant"
            )
        )
    )

    mode = (
        parser
        .add_mutually_exclusive_group()
    )

    mode.add_argument(
        "--resident",
        action="store_true",
        help=(
            "Постоянный "
            "wake-listener."
        ),
    )

    mode.add_argument(
        "--voice",
        action="store_true",
        help=(
            "Голосовой режим "
            "с консолью."
        ),
    )

    mode.add_argument(
        "--chat",
        action="store_true",
        help=(
            "Клавиатура + TTS."
        ),
    )

    mode.add_argument(
        "--text",
        action="store_true",
        help=(
            "Клавиатура "
            "без TTS."
        ),
    )

    mode.add_argument(
        "--install-startup",
        action="store_true",
        help=(
            "Добавить JARVIS "
            "в Startup."
        ),
    )

    mode.add_argument(
        "--remove-startup",
        action="store_true",
        help=(
            "Удалить JARVIS "
            "из Startup."
        ),
    )

    return parser


# =============================================================
# MAIN
# =============================================================


def main():
    parser = (
        build_parser()
    )

    args = (
        parser.parse_args()
    )

    if args.install_startup:
        install_startup()
        return 0

    if args.remove_startup:
        remove_startup()
        return 0

    resident_mode = (
        args.resident
        or not (
            args.voice
            or args.chat
            or args.text
        )
    )

    instance_guard = None

    if resident_mode:
        instance_guard = JarvisInstanceGuard()

        if not instance_guard.acquire():
            print(
                "JARVIS уже запущен."
            )
            return 0

    try:
        try:
            jarvis = Jarvis()

        except Exception as exc:
            print(
                "JARVIS START ERROR:",
                exc,
            )

            return 1

        if args.text:
            keyboard_mode(
                jarvis,
                speak=False,
            )

            return 0

        if args.chat:
            keyboard_mode(
                jarvis,
                speak=True,
            )

            return 0

        return voice_mode(
            jarvis,
            resident=resident_mode,
        )

    finally:
        if instance_guard is not None:
            instance_guard.release()


if __name__ == "__main__":
    raise SystemExit(
        main()
    )

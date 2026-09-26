# JARVIS-TOOLS-v0.8.12-UNICODE-PASTE

import ctypes
from ctypes import wintypes
import datetime as dt
import os
import re
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from urllib.parse import quote_plus

try:
    from PIL import ImageGrab
except ImportError:
    ImageGrab = None

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None

try:
    import pyautogui
    import win32clipboard
except ImportError:
    pyautogui = None
    win32clipboard = None


TOOLS_CODE_VERSION = "JARVIS-TOOLS-v0.8.12-UNICODE-PASTE"


class ToolError(RuntimeError):
    pass


class WindowsTools:
    SW_HIDE = 0
    SW_SHOWNORMAL = 1
    SW_SHOWMINIMIZED = 2
    SW_SHOWMAXIMIZED = 3
    SW_RESTORE = 9

    WM_CLOSE = 0x0010

    def computer_power(self, restart=False):
        """Request an immediate Windows shutdown/restart without a shell."""
        if os.name != "nt":
            raise ToolError("Команда питания доступна только в Windows.")
        executable = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "shutdown.exe"
        if not executable.is_file():
            raise ToolError("Windows shutdown.exe не найден.")
        subprocess.Popen(
            [str(executable), "/r" if restart else "/s", "/t", "0"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return "Перезагружаю компьютер." if restart else "Выключаю компьютер."

    def __init__(self, config, base_dir):
        self.config = config
        self.base_dir = Path(base_dir)

        self.screenshot_dir = (
            self.base_dir / "screenshots"
        )

        self.screenshot_dir.mkdir(
            exist_ok=True
        )

        self.aliases = {
            "google chrome": "chrome",
            "chrome": "chrome",
            "хром": "chrome",

            "opera gx": "opera_gx",
            "opera": "opera_gx",
            "опера": "opera_gx",

            "microsoft edge": "edge",
            "edge": "edge",
            "эдж": "edge",

            "mozilla firefox": "firefox",
            "firefox": "firefox",
            "фаерфокс": "firefox",
            "brave": "brave",
            "брейв": "brave",
            "vivaldi": "vivaldi",
            "вивальди": "vivaldi",
            "яндекс браузер": "yandex",
            "яндекс": "yandex",
            "chromium": "chromium",
            "хромиум": "chromium",

            "стим": "steam",
            "steam": "steam",

            "дота": "dota2",
            "доту": "dota2",
            "доте": "dota2",
            "dota": "dota2",
            "dota 2": "dota2",

            "soundpad": "soundpad",
            "саундпад": "soundpad",
            "саунд пад": "soundpad",
            "lossless scaling": "lossless_scaling",
            "лосслесс скейлинг": "lossless_scaling",
            "лослес скейлинг": "lossless_scaling",
            "counter strike 2": "cs2",
            "counter-strike 2": "cs2",
            "counter strike": "cs2",
            "кс 2": "cs2",
            "кс2": "cs2",
            "контр страйк 2": "cs2",
            "telegram": "ayugram",
            "телеграм": "ayugram",
            "телега": "ayugram",
            "ayugram": "ayugram",
            "аюграм": "ayugram",
            "аю грам": "ayugram",
            "телеграмм": "ayugram",
            "теле грам": "ayugram",
            "телегу": "ayugram",
            "телеграме": "ayugram",
            "а ю грам": "ayugram",
            "а ю грамм": "ayugram",
            "библиотека steam": "steam_library",
            "библиотека стим": "steam_library",
            "библиотеку в steam": "steam_library",
            "библиотеку в стиме": "steam_library",

            "дискорд": "discord",
            "discord": "discord",
            "дс": "discord",

            "калькулятор": "calculator",
            "calculator": "calculator",
            "calc": "calculator",

            "блокнот": "notepad",
            "notepad": "notepad",

            "проводник": "explorer",
            "explorer": "explorer",

            "командная строка": "cmd",
            "cmd": "cmd",

            "powershell": "powershell",
            "пауэршелл": "powershell",

            "visual studio code": "vscode",
            "vs code": "vscode",
            "vscode": "vscode",
            "код": "vscode",
        }

        self.window_hints = {
            "chrome": [
                "google chrome",
                "chrome",
            ],

            "opera_gx": [
                "opera gx",
                "opera",
            ],

            "edge": [
                "microsoft edge",
                "edge",
            ],

            "firefox": ["mozilla firefox", "firefox"],
            "brave": ["brave"],
            "vivaldi": ["vivaldi"],
            "yandex": ["yandex", "яндекс"],
            "chromium": ["chromium"],

            "discord": [
                "discord",
            ],

            "steam": [
                "steam",
            ],

            "dota2": [
                "dota 2",
            ],

            "soundpad": ["soundpad"],
            "lossless_scaling": ["lossless scaling"],
            "cs2": ["counter-strike 2", "cs2"],
            "ayugram": ["ayugram", "telegram"],
            "settings": ["параметры", "settings", "настройки"],

            "calculator": [
                "калькулятор",
                "calculator",
            ],

            "notepad": [
                "блокнот",
                "notepad",
            ],

            "explorer": [
                "проводник",
                "explorer",
            ],

            "vscode": [
                "visual studio code",
                " - code",
                "code",
            ],
        }

        self.process_names = {
            "chrome": "chrome.exe",
            "opera_gx": "opera.exe",
            "edge": "msedge.exe",
            "firefox": "firefox.exe",
            "brave": "brave.exe",
            "vivaldi": "vivaldi.exe",
            "yandex": "browser.exe",
            "chromium": "chromium.exe",
            "steam": "steam.exe",
            "dota2": "dota2.exe",
            "soundpad": "Soundpad.exe",
            "lossless_scaling": "LosslessScaling.exe",
            "cs2": "cs2.exe",
            "ayugram": "AyuGram.exe",
            "discord": "Discord.exe",
            "calculator": "CalculatorApp.exe",
            "notepad": "notepad.exe",
            "cmd": "cmd.exe",
            "powershell": "powershell.exe",
            "vscode": "Code.exe",
        }

    @staticmethod
    def _norm(text):
        return " ".join(
            (text or "")
            .lower()
            .strip()
            .split()
        )

    def canonical_app(self, name):
        normalized = self._norm(name)

        return self.aliases.get(
            normalized,
            normalized,
        )

    def known_app_from_text(self, text):
        text = self._norm(text)

        for alias in sorted(
            self.aliases,
            key=len,
            reverse=True,
        ):
            if re.search(
                rf"(?<!\w){re.escape(alias)}(?!\w)",
                text,
            ):
                return self.aliases[alias]

        return None

    # ========================================================
    # APPLICATIONS
    # ========================================================

    def open_app(self, app: str) -> str:
        """
        Open an application.

        Known:
        dota2
        discord
        steam
        vscode
        calculator
        notepad
        explorer
        """

        canonical = self.canonical_app(
            app
        )

        # Existing visible applications must be restored/focused instead of
        # launching another window. Tray-only apps fall through to their exe,
        # whose single-instance handler restores the hidden window.
        if canonical != "steam_library":
            try:
                hwnd = self._find_window(canonical)
            except ToolError:
                hwnd = None
            if hwnd:
                user32 = self._user32()
                user32.ShowWindow(hwnd, self.SW_RESTORE)
                user32.SetForegroundWindow(hwnd)
                return f"Переключился на {self._title(hwnd)}."

        # --------------------------------------------
        # STEAM APPLICATIONS
        # --------------------------------------------

        steam_apps = {
            "dota2": (570, "Dota 2"),
            "soundpad": (629520, "Soundpad"),
            "lossless_scaling": (993090, "Lossless Scaling"),
            "cs2": (730, "Counter-Strike 2"),
        }

        if canonical in steam_apps:
            app_id, display_name = steam_apps[canonical]
            os.startfile(f"steam://rungameid/{app_id}")
            return f"Запускаю {display_name}."

        if canonical == "steam_library":
            os.startfile("steam://open/games")
            return "Открываю библиотеку Steam."

        # --------------------------------------------
        # CONFIG APPS
        # --------------------------------------------

        command = (
            self.config
            .get("apps", {})
            .get(canonical)
        )

        if command:
            command = os.path.expandvars(
                command
            )

            if Path(command).exists():
                subprocess.Popen(
                    [command],
                    shell=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            else:
                # Legacy config entries may contain fixed arguments,
                # for example Discord Update.exe --processStart.
                subprocess.Popen(
                    command,
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            return f"Открыл {app}."

        # --------------------------------------------
        # WINDOWS FALLBACK
        # --------------------------------------------

        try:
            os.startfile(app)

            return (
                "Передал Windows команду "
                f"открыть {app}."
            )

        except Exception as exc:
            raise ToolError(
                f"Не удалось открыть "
                f"«{app}»: {exc}"
            )

    def close_app(self, app: str) -> str:
        """
        Полное завершение процесса.

        Для обычного закрытия окна лучше
        использовать close_window().
        """

        canonical = self.canonical_app(
            app
        )

        if canonical == "explorer":
            raise ToolError(
                "Проводник Windows "
                "намеренно не завершаю."
            )

        process = self.process_names.get(
            canonical
        )

        if not process:
            raise ToolError(
                f"Не знаю процесс для "
                f"«{app}»."
            )

        result = subprocess.run(
            [
                "taskkill",
                "/IM",
                process,
                "/T",
            ],
            capture_output=True,
            text=True,
            creationflags=getattr(
                subprocess,
                "CREATE_NO_WINDOW",
                0,
            ),
        )

        if result.returncode:
            raise ToolError(
                f"Не удалось закрыть "
                f"«{app}»."
            )

        return f"Закрыл {app}."

    # ========================================================
    # WINDOWS API
    # ========================================================

    def _user32(self):
        if os.name != "nt":
            raise ToolError(
                "Управление окнами "
                "доступно только в Windows."
            )

        return ctypes.windll.user32

    def _windows(self):
        user32 = self._user32()

        windows = []

        CALLBACK = ctypes.WINFUNCTYPE(
            ctypes.c_bool,
            ctypes.c_void_p,
            ctypes.c_void_p,
        )

        def enum_callback(
            hwnd,
            lparam,
        ):
            if not user32.IsWindowVisible(
                hwnd
            ):
                return True

            length = (
                user32
                .GetWindowTextLengthW(
                    hwnd
                )
            )

            if not length:
                return True

            buffer = (
                ctypes
                .create_unicode_buffer(
                    length + 1
                )
            )

            user32.GetWindowTextW(
                hwnd,
                buffer,
                length + 1,
            )

            title = buffer.value.strip()

            if title:
                windows.append(
                    (
                        int(hwnd),
                        title,
                    )
                )

            return True

        user32.EnumWindows(
            CALLBACK(
                enum_callback
            ),
            0,
        )

        return windows

    def _find_window(
        self,
        target="active",
    ):
        user32 = self._user32()

        target = self._norm(
            target
        )

        # --------------------------------------------
        # ACTIVE WINDOW
        # --------------------------------------------

        if target in (
            "",
            "active",
            "активное",
            "активное окно",
            "это окно",
            "текущее окно",
        ):
            hwnd = int(
                user32
                .GetForegroundWindow()
            )

            if not hwnd:
                raise ToolError(
                    "Не вижу активного окна."
                )

            return hwnd

        # --------------------------------------------
        # NAMED WINDOW
        # --------------------------------------------

        canonical = self.canonical_app(
            target
        )

        hints = self.window_hints.get(
            canonical,
            [target],
        )

        for hwnd, title in self._windows():
            low = title.lower()

            if any(
                hint in low
                for hint in hints
            ):
                return hwnd

        raise ToolError(
            f"Не нашёл окно «{target}»."
        )

    def _title(self, hwnd):
        user32 = self._user32()

        length = (
            user32
            .GetWindowTextLengthW(
                hwnd
            )
        )

        buffer = (
            ctypes
            .create_unicode_buffer(
                max(
                    1,
                    length + 1,
                )
            )
        )

        user32.GetWindowTextW(
            hwnd,
            buffer,
            len(buffer),
        )

        return (
            buffer.value
            or "без названия"
        )

    # ========================================================
    # ACTIVE WINDOW
    # ========================================================

    def get_active_window(self) -> str:
        """
        Return the title of the currently
        focused foreground window.
        """

        hwnd = self._find_window(
            "active"
        )

        title = self._title(
            hwnd
        )

        return (
            f"Активное окно: {title}."
        )

    def list_windows(self) -> str:
        """Return unique titles of all visible top-level windows."""
        titles = []
        seen = set()
        for _hwnd, title in self._windows():
            normalized = self._norm(title)
            if normalized and normalized not in seen:
                seen.add(normalized)
                titles.append(title)
        if not titles:
            return "Открытых окон с названиями не найдено."
        return "Открытые окна: " + "; ".join(titles) + "."

    def click_ui_element(self, label: str) -> str:
        """Click a visible Win32 child control by its accessible text."""
        wanted = self._norm(label)
        if not wanted:
            raise ToolError("Не указано, на какой элемент нажать.")

        user32 = self._user32()
        parent = int(user32.GetForegroundWindow())
        matches = []
        CALLBACK = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def enum_child(hwnd, _lparam):
            length = user32.GetWindowTextLengthW(hwnd)
            if length:
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                text = buffer.value.strip()
                normalized = self._norm(text)
                if normalized and (wanted == normalized or wanted in normalized):
                    matches.append((int(hwnd), text))
            return True

        user32.EnumChildWindows(parent, CALLBACK(enum_child), 0)
        if not matches:
            raise ToolError(
                f"Не нашёл доступный для нажатия элемент «{label}» в активном окне."
            )

        hwnd, text = min(matches, key=lambda item: len(item[1]))
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            raise ToolError(f"Не удалось определить положение элемента «{text}».")
        x = (rect.left + rect.right) // 2
        y = (rect.top + rect.bottom) // 2
        user32.SetCursorPos(x, y)
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        user32.mouse_event(0x0004, 0, 0, 0, 0)
        return f"Нажал «{text}»."

    @staticmethod
    def _require_keyboard():
        if pyautogui is None or win32clipboard is None:
            raise ToolError("Для клавиатурного управления нужны pyautogui и pywin32.")

    def press_key(self, key: str) -> str:
        self._require_keyboard()
        aliases = {
            "пробел": "space", "спейс": "space", "space": "space",
            "энтер": "enter", "ентер": "enter", "enter": "enter", "ввод": "enter",
            "эскейп": "esc", "эск": "esc", "escape": "esc", "esc": "esc",
            "таб": "tab", "tab": "tab",
            "стрелка вверх": "up", "вверх": "up",
            "стрелка вниз": "down", "вниз": "down",
            "стрелка влево": "left", "влево": "left",
            "стрелка вправо": "right", "вправо": "right",
            "бэкспейс": "backspace", "backspace": "backspace",
            "делит": "delete", "delete": "delete",
        }
        normalized = self._norm(key).replace("клавишу ", "").replace("кнопку ", "")
        resolved = aliases.get(normalized)
        if not resolved:
            raise ToolError(f"Не знаю клавишу «{key}».")
        pyautogui.press(resolved)
        return f"Нажал клавишу {normalized}."

    def type_text(self, text: str, submit=False) -> str:
        self._require_keyboard()
        value = str(text or "").strip()
        if not value:
            raise ToolError("Не указан текст для ввода.")

        old_clipboard = None
        had_text = False
        try:
            win32clipboard.OpenClipboard()
            try:
                if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                    old_clipboard = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
                    had_text = True
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(value, win32clipboard.CF_UNICODETEXT)
            finally:
                win32clipboard.CloseClipboard()
            pyautogui.hotkey("ctrl", "v")
            if submit:
                pyautogui.press("enter")
            time.sleep(0.08)
        finally:
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                if had_text:
                    win32clipboard.SetClipboardText(old_clipboard, win32clipboard.CF_UNICODETEXT)
            finally:
                win32clipboard.CloseClipboard()
        return f"Typed text: {value}"

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = (
                ("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", wintypes.WPARAM),
            )

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = (
                ("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", wintypes.WPARAM),
            )

        class HARDWAREINPUT(ctypes.Structure):
            _fields_ = (
                ("uMsg", wintypes.DWORD),
                ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD),
            )

        class INPUT_UNION(ctypes.Union):
            _fields_ = (("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT))

        class INPUT(ctypes.Structure):
            _anonymous_ = ("union",)
            _fields_ = (("type", wintypes.DWORD), ("union", INPUT_UNION))

        units = value.encode("utf-16-le")
        user32 = ctypes.windll.user32
        for index in range(0, len(units), 2):
            code_unit = int.from_bytes(units[index:index + 2], "little")
            for flags in (0x0004, 0x0004 | 0x0002):
                event = INPUT(type=1, ki=KEYBDINPUT(0, code_unit, flags, 0, 0))
                if user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT)) != 1:
                    raise ToolError("Windows не приняла Unicode-ввод.")
        if submit:
            pyautogui.press("enter")
        return f"Ввёл текст: {value}"

    def browser_search(self, query: str, browser="chrome") -> str:
        query = str(query or "").strip()
        if not query:
            raise ToolError("Не указан поисковый запрос.")
        try:
            self.focus_window(browser)
        except ToolError:
            self.open_app(browser)
            time.sleep(1.0)
            self.focus_window(browser)
        url = "https://www.google.com/search?q=" + quote_plus(query)
        canonical = self.canonical_app(browser)
        command = self.config.get("apps", {}).get(canonical)
        if canonical == "chrome" and command and Path(os.path.expandvars(command)).exists():
            subprocess.Popen(
                [os.path.expandvars(command), "--new-tab", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            webbrowser.open_new_tab(url)
        return f"Ищу в браузере: {query}"

    def _window_rect(self, hwnd):
        rect = wintypes.RECT()
        if not self._user32().GetWindowRect(hwnd, ctypes.byref(rect)):
            raise ToolError("Не удалось определить границы окна.")
        if rect.right <= rect.left or rect.bottom <= rect.top:
            raise ToolError("Окно имеет некорректные границы.")
        return rect.left, rect.top, rect.right, rect.bottom

    def _click_screen_point(self, x, y):
        user32 = self._user32()
        user32.SetCursorPos(int(x), int(y))
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        user32.mouse_event(0x0004, 0, 0, 0, 0)

    def click_colored_button(
        self,
        color="green",
        target="active",
        region="any",
    ) -> str:
        """Find and click a button-like colored region inside one window."""
        if ImageGrab is None or cv2 is None or np is None:
            raise ToolError("Для визуального управления нужны Pillow, OpenCV и NumPy.")

        ranges = {
            "green": ((35, 65, 65), (95, 255, 255)),
            "зелёная": ((35, 65, 65), (95, 255, 255)),
            "зеленая": ((35, 65, 65), (95, 255, 255)),
            "blue": ((90, 65, 65), (135, 255, 255)),
            "синяя": ((90, 65, 65), (135, 255, 255)),
        }
        key = self._norm(color)
        if key not in ranges:
            raise ToolError("Пока поддерживаются зелёные и синие кнопки.")

        hwnd = self._find_window(target)
        user32 = self._user32()
        user32.ShowWindow(hwnd, self.SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.25)
        left, top, right, bottom = self._window_rect(hwnd)
        image = np.array(ImageGrab.grab(bbox=(left, top, right, bottom)))
        hsv = cv2.cvtColor(image[:, :, :3], cv2.COLOR_RGB2HSV)
        lower, upper = ranges[key]
        mask = cv2.inRange(hsv, np.array(lower), np.array(upper))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        width = right - left
        height = bottom - top
        candidates = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            area = w * h
            if area < 900 or w < 55 or h < 18 or w / max(1, h) > 15:
                continue
            if region == "bottom_right" and (x < width * 0.45 or y < height * 0.45):
                continue
            fill = cv2.contourArea(contour) / max(1.0, float(area))
            if fill < 0.30:
                continue
            candidates.append((area * fill, x, y, w, h))

        if not candidates:
            raise ToolError(f"Не нашёл {color} кнопку в окне {self._title(hwnd)}.")

        _score, x, y, w, h = max(candidates, key=lambda item: item[0])
        click_x = left + x + w // 2
        click_y = top + y + h // 2
        self._click_screen_point(click_x, click_y)
        return f"Нажал {color} кнопку в окне {self._title(hwnd)}."

    def start_dota_match_search(self) -> str:
        """Click up to two green bottom-right Dota buttons with fresh detection."""
        clicks = 0
        errors = []
        for _attempt in range(2):
            try:
                self.click_colored_button(
                    color="green",
                    target="dota2",
                    region="bottom_right",
                )
                clicks += 1
                time.sleep(1.15)
            except ToolError as exc:
                errors.append(str(exc))
                break
        if clicks == 2:
            return "Дважды нажал зелёную кнопку в Dota 2."
        if clicks == 1:
            return "Нажал первую зелёную кнопку Dota 2, но вторую не нашёл."
        raise ToolError(errors[-1] if errors else "Не нашёл кнопку поиска игры в Dota 2.")

    def start_apple_game_bot(self) -> str:
        script = self.base_dir / "apple_game_bot.py"
        stop_file = self.base_dir / "apple_game_bot.stop"
        pid_file = self.base_dir / "apple_game_bot.pid"
        if not script.exists():
            raise ToolError("Не найден apple_game_bot.py.")
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text(encoding="utf-8").strip())
                handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
                if handle:
                    ctypes.windll.kernel32.CloseHandle(handle)
                    return "Контроллер игры с яблоками уже работает."
            except (OSError, ValueError):
                pass
            pid_file.unlink(missing_ok=True)
        stop_file.unlink(missing_ok=True)
        subprocess.Popen(
            [sys.executable, str(script), "--delay", "3"],
            cwd=str(self.base_dir),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return "Через три секунды начну отбивать яблоки. Для остановки нажми F8."

    def stop_apple_game_bot(self) -> str:
        (self.base_dir / "apple_game_bot.stop").write_text("stop", encoding="utf-8")
        return "Останавливаю контроллер игры с яблоками."

    # ========================================================
    # MINIMIZE
    # ========================================================

    def minimize_window(
        self,
        target: str = "active",
    ) -> str:
        """
        Minimize a window.

        target:
        active
        discord
        steam
        dota2
        vscode
        etc.
        """

        hwnd = self._find_window(
            target
        )

        title = self._title(
            hwnd
        )

        self._user32().ShowWindow(
            hwnd,
            self.SW_SHOWMINIMIZED,
        )

        return (
            f"Свернул {title}."
        )

    # ========================================================
    # MAXIMIZE
    # ========================================================

    def maximize_window(
        self,
        target: str = "active",
    ) -> str:
        """
        Maximize a window.
        """

        hwnd = self._find_window(
            target
        )

        title = self._title(
            hwnd
        )

        user32 = self._user32()

        user32.ShowWindow(
            hwnd,
            self.SW_SHOWMAXIMIZED,
        )

        user32.SetForegroundWindow(
            hwnd
        )

        return (
            f"Развернул {title}."
        )

    # ========================================================
    # RESTORE
    # ========================================================

    def restore_window(
        self,
        target: str = "active",
    ) -> str:
        """
        Restore a minimized window
        and bring it forward.
        """

        hwnd = self._find_window(
            target
        )

        title = self._title(
            hwnd
        )

        user32 = self._user32()

        user32.ShowWindow(
            hwnd,
            self.SW_RESTORE,
        )

        user32.SetForegroundWindow(
            hwnd
        )

        return (
            f"Восстановил {title}."
        )

    # ========================================================
    # FOCUS
    # ========================================================

    def focus_window(
        self,
        target: str,
    ) -> str:
        """
        Bring a named application window
        to the foreground.
        """

        hwnd = self._find_window(
            target
        )

        title = self._title(
            hwnd
        )

        user32 = self._user32()

        user32.ShowWindow(
            hwnd,
            self.SW_RESTORE,
        )

        user32.SetForegroundWindow(
            hwnd
        )

        return (
            f"Переключился на {title}."
        )

    # ========================================================
    # CLOSE WINDOW
    # ========================================================

    def close_window(
        self,
        target: str = "active",
    ) -> str:
        """
        Normal Windows WM_CLOSE.

        Это НЕ taskkill.
        """

        hwnd = self._find_window(
            target
        )

        title = self._title(
            hwnd
        )

        self._user32().PostMessageW(
            hwnd,
            self.WM_CLOSE,
            0,
            0,
        )

        return (
            f"Закрыл окно {title}."
        )

    # ========================================================
    # WINDOWS SYSTEM PAGES
    # ========================================================

    def open_system_item(
        self,
        target: str,
    ) -> str:
        """Открывает только заранее разрешённые страницы Windows."""

        target = self._norm(
            target
        )

        settings_uris = {
            "settings": "ms-settings:",
            "sound_settings": "ms-settings:sound",
            "display_settings": "ms-settings:display",
            "bluetooth_settings": "ms-settings:bluetooth",
            "windows_update": "ms-settings:windowsupdate",
        }

        display_names = {
            "settings": "настройки Windows",
            "sound_settings": "настройки звука",
            "display_settings": "настройки экрана",
            "bluetooth_settings": "настройки Bluetooth",
            "windows_update": "Центр обновления Windows",
            "control_panel": "панель управления Windows",
            "task_manager": "диспетчер задач",
            "device_manager": "диспетчер устройств",
            "disk_management": "управление дисками",
            "network_connections": "сетевые подключения",
            "programs_features": "программы и компоненты",
            "services": "службы Windows",
            "power_options": "параметры питания",
            "nvidia_control_panel": "панель управления NVIDIA",
        }

        if target in settings_uris:
            os.startfile(
                settings_uris[target]
            )

            return (
                "Открыл "
                f"{display_names[target]}."
            )

        commands = {
            "control_panel": [
                "control.exe",
            ],
            "task_manager": [
                "taskmgr.exe",
            ],
            "device_manager": [
                "mmc.exe",
                "devmgmt.msc",
            ],
            "disk_management": [
                "mmc.exe",
                "diskmgmt.msc",
            ],
            "network_connections": [
                "control.exe",
                "ncpa.cpl",
            ],
            "programs_features": [
                "control.exe",
                "appwiz.cpl",
            ],
            "services": [
                "mmc.exe",
                "services.msc",
            ],
            "power_options": [
                "control.exe",
                "powercfg.cpl",
            ],
        }

        if target == "nvidia_control_panel":
            return self._open_nvidia_control_panel()

        command = commands.get(
            target
        )

        if not command:
            raise ToolError(
                "Неизвестный системный раздел: "
                f"{target}."
            )

        subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(
                subprocess,
                "CREATE_NO_WINDOW",
                0,
            ),
        )

        return (
            "Открыл "
            f"{display_names[target]}."
        )

    def _open_nvidia_control_panel(
        self,
    ) -> str:
        candidates = (
            Path(
                r"C:\Program Files\NVIDIA Corporation\Control Panel Client\nvcplui.exe"
            ),
            Path(
                r"C:\Windows\System32\nvcplui.exe"
            ),
        )

        executable = shutil.which(
            "nvcplui.exe"
        )

        for candidate in candidates:
            if candidate.exists():
                executable = str(
                    candidate
                )
                break

        if executable:
            subprocess.Popen(
                [executable],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(
                    subprocess,
                    "CREATE_NO_WINDOW",
                    0,
                ),
            )

            return (
                "Открыл панель управления NVIDIA."
            )

        powershell = (
            shutil.which("powershell.exe")
            or shutil.which("powershell")
        )

        if powershell:
            script = (
                "Get-StartApps | Where-Object { "
                "$_.Name -match 'NVIDIA' } | "
                "Select-Object -First 1 -ExpandProperty AppID"
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
                timeout=4.0,
                creationflags=getattr(
                    subprocess,
                    "CREATE_NO_WINDOW",
                    0,
                ),
            )

            app_id = (
                result.stdout
                or ""
            ).strip()

            if result.returncode == 0 and app_id:
                subprocess.Popen(
                    [
                        "explorer.exe",
                        "shell:AppsFolder\\"
                        + app_id,
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

                return (
                    "Открыл панель управления NVIDIA."
                )

        raise ToolError(
            "Панель управления NVIDIA не найдена. "
            "Проверьте, установлена ли она вместе с драйвером."
        )

    # ========================================================
    # FOLDERS
    # ========================================================

    def open_folder(
        self,
        target: str,
    ) -> str:
        target = self._norm(
            target
        )

        user_profile = Path(
            os.environ.get(
                "USERPROFILE",
                str(Path.home()),
            )
        )

        folders = {
            "downloads": user_profile / "Downloads",
            "documents": user_profile / "Documents",
            "desktop": user_profile / "Desktop",
            "pictures": user_profile / "Pictures",
            "videos": user_profile / "Videos",
            "music": user_profile / "Music",
            "project": self.base_dir,
            "screenshots": self.screenshot_dir,
        }

        display_names = {
            "downloads": "Загрузки",
            "documents": "Документы",
            "desktop": "Рабочий стол",
            "pictures": "Изображения",
            "videos": "Видео",
            "music": "Музыку",
            "project": "папку JARVIS",
            "screenshots": "папку скриншотов",
            "recycle_bin": "Корзину",
        }

        if target == "recycle_bin":
            subprocess.Popen(
                [
                    "explorer.exe",
                    "shell:RecycleBinFolder",
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            return "Открыл Корзину."

        path = folders.get(
            target
        )

        if path is None:
            raise ToolError(
                f"Неизвестная папка: {target}."
            )

        if not path.exists():
            raise ToolError(
                "Папка не найдена: "
                f"{path}"
            )

        os.startfile(
            str(path)
        )

        return (
            "Открыл "
            f"{display_names[target]}."
        )

    # ========================================================
    # WEB
    # ========================================================

    def open_url(
        self,
        url: str,
    ) -> str:
        """
        Open URL in default browser.
        """

        if not url.startswith(
            (
                "http://",
                "https://",
            )
        ):
            url = (
                "https://"
                + url
            )

        webbrowser.open(
            url
        )

        return (
            f"Открыл {url}"
        )

    def web_search(
        self,
        query: str,
    ) -> str:
        """
        Search Google.
        """

        url = (
            "https://www.google.com/"
            "search?q="
            + quote_plus(
                query
            )
        )

        webbrowser.open(
            url
        )

        return (
            f"Открыл поиск: {query}"
        )

    # ========================================================
    # SCREENSHOT
    # ========================================================

    def take_screenshot(
        self,
    ) -> str:
        """
        Screenshot all monitors.
        """

        if ImageGrab is None:
            raise ToolError(
                "Не установлен Pillow."
            )

        name = (
            "screenshot_"
            + dt.datetime.now().strftime(
                "%Y-%m-%d_%H-%M-%S"
            )
            + ".png"
        )

        path = (
            self.screenshot_dir
            / name
        )

        ImageGrab.grab(
            all_screens=True
        ).save(
            path
        )

        return (
            "Скриншот сохранён: "
            f"{path}"
        )

    # ========================================================
    # VOLUME
    # ========================================================

    def set_volume(
        self,
        value: int,
    ) -> str:
        """
        Approximate Windows volume
        from 0 to 100.
        """

        try:
            import keyboard

        except ImportError:
            raise ToolError(
                "Не установлен "
                "пакет keyboard."
            )

        value = max(
            0,
            min(
                100,
                int(value),
            ),
        )

        for _ in range(55):
            keyboard.send(
                "volume down"
            )

        for _ in range(
            round(
                value / 2
            )
        ):
            keyboard.send(
                "volume up"
            )

        return (
            "Громкость примерно "
            f"{value}%."
        )

    # ========================================================
    # TIME
    # ========================================================

    def get_time(
        self,
    ) -> str:
        """
        Current local time.
        """

        return (
            dt.datetime.now()
            .strftime(
                "Сейчас %H:%M:%S."
            )
        )

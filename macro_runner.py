# JARVIS-MACROS-v0.2.1-VISIBLE-INPUTS

import argparse
from assistant_identity import display_names, names as assistant_names
import ctypes
import json
import os
import re
import threading
import time
import urllib.request
import winreg
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

import pyautogui

VERSION = "JARVIS-MACROS-v0.3.0-APP-LAUNCH-HELP"
BASE_DIR = Path(__file__).resolve().parent
SCENARIOS_DIR = BASE_DIR / "сценарии"
PHRASES_FILE = BASE_DIR / "macro_phrases.json"
ALLOWED = {"ожидание", "клавиша", "удержание", "сочетание", "текст", "курсор", "щелчок", "повтор"}


def launch_application(target):
    path = Path(str(target).strip().strip('"'))
    if not path.is_file() or path.suffix.casefold() not in {".exe", ".lnk", ".url"}:
        raise ValueError("Выберите существующий .exe или ярлык .lnk/.url игры.")
    os.startfile(str(path.resolve()))


def close_saved_application(scenario_path):
    """Close the executable used by a saved launch scenario."""
    path = Path(scenario_path).resolve()
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("тип") != "launch":
        raise ValueError("Антикоманда доступна только для запуска приложений.")
    target = Path(str(document.get("файл", "")).strip().strip('"')).resolve()
    if not target.is_file():
        raise FileNotFoundError("Файл приложения больше не найден.")
    executable = target
    if target.suffix.casefold() == ".lnk":
        script = "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($args[0]);[Console]::Write($s.TargetPath)"
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script, str(target)],
                                capture_output=True, text=True, encoding="utf-8", errors="replace",
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=15)
        resolved = Path(result.stdout.strip())
        if result.returncode != 0 or not resolved.name:
            raise RuntimeError("Не удалось определить программу внутри ярлыка.")
        executable = resolved
    if executable.suffix.casefold() != ".exe":
        raise ValueError("Автоматическое закрытие поддерживается для EXE и ярлыков на EXE.")
    result = subprocess.run(["taskkill.exe", "/IM", executable.name, "/T"], capture_output=True,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode not in (0, 128):
        raise RuntimeError("Windows не смогла закрыть приложение.")


def explicit_plan(prompt):
    """Small documented command language, no model required."""
    actions = []
    for line in re.split(r"[;\n]+", prompt):
        line = line.strip()
        if not line:
            continue
        match = re.fullmatch(r"(?:жди|ожидание)\s+(\d+(?:[.,]\d+)?)", line, re.I)
        if match:
            actions.append({"действие": "ожидание", "секунды": float(match[1].replace(",", "."))})
            continue
        match = re.fullmatch(r"нажми\s+([a-z0-9_+]+)", line, re.I)
        if match:
            keys = match[1].lower().split("+")
            if any(key not in pyautogui.KEYBOARD_KEYS for key in keys):
                raise ValueError(f"Неизвестная клавиша: {match[1]}")
            actions.append({"действие": "клавиша", "клавиша": keys[0]} if len(keys) == 1
                           else {"действие": "сочетание", "клавиши": keys})
            continue
        match = re.fullmatch(r"удерживай\s+([a-z0-9_]+)\s+(\d+(?:[.,]\d+)?)", line, re.I)
        if match and match[1].lower() in pyautogui.KEYBOARD_KEYS:
            actions.append({"действие": "удержание", "клавиша": match[1].lower(), "секунды": float(match[2].replace(",", "."))})
            continue
        match = re.fullmatch(r"(курсор|клик)\s+(\d+)\s+(\d+)", line, re.I)
        if match:
            actions.append({"действие": "курсор" if match[1].lower() == "курсор" else "щелчок", "x": int(match[2]), "y": int(match[3])})
            continue
        match = re.fullmatch(r"текст\s+(.+)", line, re.I)
        if match and match[1].isascii():
            actions.append({"действие": "текст", "текст": match[1]})
            continue
        raise ValueError(f"Не понял строку «{line}». Откройте «Команды и примеры».")
    if not actions:
        raise ValueError("Введите хотя бы одну команду.")
    return _validate(actions)
ONLINE_MARKERS = {
    "dota", "дота", "counter-strike", "counter strike", "cs2", "кс 2",
    "valorant", "fortnite", "форта", "apex", "warzone", "roblox", "роблокс",
    "league of legends", "overwatch", "pubg", "minecraft server", "онлайн",
    "сетевой", "мультиплеер", "discord", "дискорд",
}


def normalize_phrase(text):
    text = str(text or "").casefold().replace("ё", "е")
    text = re.sub(r"[^a-zа-я0-9]+", " ", text)
    return " ".join(text.split())


def load_phrase_registry():
    try:
        data = json.loads(PHRASES_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def save_phrase_binding(phrase, scenario_path):
    normalized = normalize_phrase(phrase)
    if not normalized:
        raise ValueError("Введите кодовую фразу.")
    registry = load_phrase_registry()
    registry[normalized] = str(Path(scenario_path).resolve())
    PHRASES_FILE.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def windows_colors():
    dark = True
    accent = "#20a83a"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            light, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            dark = not bool(light)
    except OSError:
        pass
    try:
        color = ctypes.c_uint()
        opaque = ctypes.c_bool()
        if ctypes.windll.dwmapi.DwmGetColorizationColor(ctypes.byref(color), ctypes.byref(opaque)) == 0:
            value = color.value
            accent = f"#{(value >> 16) & 255:02x}{(value >> 8) & 255:02x}{value & 255:02x}"
    except (AttributeError, OSError):
        pass
    if dark:
        return {"bg": "#090909", "card": "#242424", "field": "#303030", "fg": "#f2f2f2", "muted": "#aaaaaa", "accent": accent}
    return {"bg": "#f3f3f3", "card": "#e7e7e7", "field": "#d8d8d8", "fg": "#161616", "muted": "#606060", "accent": accent}


def style_input(widget, colors):
    """A clearly visible, slightly grey writable field with an accent focus."""
    def repaint(focused=False):
        if not widget.winfo_exists():
            return
        widget.configure(
            bg=colors["field"], fg=colors["fg"], insertbackground=colors["fg"],
            selectbackground=colors["accent"], selectforeground="#ffffff",
            relief="flat", bd=0, highlightthickness=2 if focused else 1,
            highlightbackground=colors["muted"], highlightcolor=colors["accent"],
        )
    repaint(False)
    widget.bind("<FocusIn>", lambda _event: repaint(True), add="+")
    widget.bind("<FocusOut>", lambda _event: repaint(False), add="+")
    return widget


def visible_windows():
    """Return selectable top-level windows as (handle, title)."""
    if os.name != "nt":
        return []
    user32 = ctypes.windll.user32
    found = []
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def collect(hwnd, _):
        if not user32.IsWindowVisible(hwnd) or user32.GetWindowTextLengthW(hwnd) <= 0:
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value.strip()
        if title and title not in {"Program Manager", "Панель управления"}:
            found.append((int(hwnd), title))
        return True

    user32.EnumWindows(callback_type(collect), 0)
    return sorted(found, key=lambda item: item[1].casefold())


def activate_window(hwnd):
    if os.name != "nt" or not hwnd or not ctypes.windll.user32.IsWindow(hwnd):
        return False
    user32 = ctypes.windll.user32
    user32.ShowWindow(hwnd, 9)  # восстановить, если окно свёрнуто
    user32.BringWindowToTop(hwnd)
    pyautogui.press("alt")  # разрешает перевод фокуса после действия пользователя
    return bool(user32.SetForegroundWindow(hwnd))


def _validate(actions, depth=0):
    if depth > 2 or not isinstance(actions, list) or len(actions) > 100:
        raise ValueError("План слишком большой или слишком глубоко вложен.")
    clean = []
    for action in actions:
        if not isinstance(action, dict) or action.get("действие") not in ALLOWED:
            raise ValueError("План содержит запрещённое действие.")
        kind = action["действие"]
        item = {"действие": kind}
        if kind == "ожидание":
            item["секунды"] = min(30.0, max(0.05, float(action.get("секунды", 1))))
        elif kind == "клавиша":
            item["клавиша"] = str(action.get("клавиша", "")).lower()[:24]
        elif kind == "удержание":
            item["клавиша"] = str(action.get("клавиша", "")).lower()[:24]
            item["секунды"] = min(30.0, max(0.05, float(action.get("секунды", 1))))
        elif kind == "сочетание":
            keys = action.get("клавиши", [])
            if not isinstance(keys, list) or not 2 <= len(keys) <= 4:
                raise ValueError("Некорректное сочетание клавиш.")
            item["клавиши"] = [str(key).lower()[:24] for key in keys]
        elif kind == "текст":
            item["текст"] = str(action.get("текст", ""))[:1000]
        elif kind in {"курсор", "щелчок"}:
            item["x"] = int(action.get("x", 0))
            item["y"] = int(action.get("y", 0))
            item["длительность"] = min(5.0, max(0.0, float(action.get("длительность", 0.2))))
        elif kind == "повтор":
            item["раз"] = min(100, max(1, int(action.get("раз", 1))))
            item["шаги"] = _validate(action.get("шаги", []), depth + 1)
        clean.append(item)
    return clean


def make_plan(prompt):
    instruction = f"""Составь безопасный макрос только для локальной офлайн-игры.
Верни строго один объект JSON вида {{"actions": [...]}} без пояснений.
Внутри actions разрешены только такие английские служебные поля:
{{"action":"wait","seconds":1}}, {{"action":"key","key":"space"}},
{{"action":"hold","key":"right","seconds":1}},
{{"action":"hotkey","keys":["ctrl","a"]}}, {{"action":"text","text":"пример"}},
{{"action":"move","x":100,"y":200,"duration":0.2}},
{{"action":"click","x":100,"y":200}},
{{"action":"repeat","count":5,"steps":[]}}.
Не создавай программный код, команды оболочки, работу с файлами или сетью.
Описание пользователя: {prompt}"""
    payload = json.dumps({
        "model": "qwen3:4b",
        "prompt": instruction,
        "stream": False,
        "format": "json",
        "think": False,
        "options": {"temperature": 0.1},
    }).encode()
    request = urllib.request.Request("http://127.0.0.1:11434/api/generate", data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=90) as response:
        result = json.load(response).get("response", "[]")
    parsed = json.loads(result)
    if isinstance(parsed, dict):
        parsed = parsed.get("actions", [])
    kinds = {"wait": "ожидание", "key": "клавиша", "hold": "удержание", "hotkey": "сочетание", "text": "текст",
             "move": "курсор", "click": "щелчок", "repeat": "повтор"}
    def translate(items):
        converted = []
        for source in items if isinstance(items, list) else []:
            kind = kinds.get(source.get("action"), source.get("действие"))
            item = {"действие": kind}
            if kind == "ожидание": item["секунды"] = source.get("seconds", source.get("секунды", 1))
            elif kind == "клавиша": item["клавиша"] = source.get("key", source.get("клавиша", ""))
            elif kind == "удержание":
                item["клавиша"] = source.get("key", source.get("клавиша", ""))
                item["секунды"] = source.get("seconds", source.get("секунды", 1))
            elif kind == "сочетание": item["клавиши"] = source.get("keys", source.get("клавиши", []))
            elif kind == "текст": item["текст"] = source.get("text", source.get("текст", ""))
            elif kind in {"курсор", "щелчок"}:
                item.update(x=source.get("x", 0), y=source.get("y", 0),
                            длительность=source.get("duration", source.get("длительность", 0.2)))
            elif kind == "повтор":
                item["раз"] = source.get("count", source.get("раз", 1))
                item["шаги"] = translate(source.get("steps", source.get("шаги", [])))
            converted.append(item)
        return converted
    plan = _validate(translate(parsed))
    if not plan:
        raise ValueError("Qwen вернул пустой план. Опишите действия немного точнее.")
    return plan


def run_actions(actions):
    for action in actions:
        kind = action["действие"]
        if kind == "ожидание": time.sleep(action["секунды"])
        elif kind == "клавиша": pyautogui.press(action["клавиша"])
        elif kind == "удержание":
            pyautogui.keyDown(action["клавиша"])
            try: time.sleep(action["секунды"])
            finally: pyautogui.keyUp(action["клавиша"])
        elif kind == "сочетание": pyautogui.hotkey(*action["клавиши"])
        elif kind == "текст": pyautogui.write(action["текст"], interval=0.02)
        elif kind == "курсор": pyautogui.moveTo(action["x"], action["y"], duration=action["длительность"])
        elif kind == "щелчок": pyautogui.click(action["x"], action["y"], duration=action["длительность"])
        elif kind == "повтор":
            for _ in range(action["раз"]): run_actions(action["шаги"])


class MacroWindow:
    def __init__(self):
        self.colors = windows_colors()
        c = self.colors
        self.root = tk.Tk(); self.root.title(display_names("Макросы и автодействия Джарвис")); self.root.geometry("900x820")
        self.root.minsize(760, 650); self.root.configure(bg=c["bg"]); self.plan = []; self.busy = False
        self.game = tk.StringVar(); self.target_name = tk.StringVar(value="Окно не выбрано")
        self.scenario_name = tk.StringVar(value="Новый сценарий")
        self.code_phrase = tk.StringVar()
        self.scenario_type = tk.StringVar(value="launch")
        self.target_hwnd = None; self.status = tk.StringVar(value="Готово")
        fg, bg, card, field, accent = c["fg"], c["bg"], c["card"], c["field"], c["accent"]
        tk.Label(self.root, text="Макросы и автодействия", font=("Segoe UI", 20, "bold"), bg=bg, fg=fg).pack(anchor="w", padx=22, pady=(20, 4))
        tk.Label(self.root, text="Запуск приложений по фразе или макросы для локальной игры. Без Qwen.", bg=bg, fg=c["muted"]).pack(anchor="w", padx=22, pady=(0, 8))
        modes = tk.Frame(self.root, bg=bg); modes.pack(fill="x", padx=22)
        for label, value in (("Запустить приложение / игру", "launch"), ("Нажатия в окне", "macro")):
            tk.Radiobutton(modes, text=label, variable=self.scenario_type, value=value, bg=bg, fg=fg,
                           selectcolor=card, activebackground=bg, activeforeground=fg).pack(side="left")
        tk.Button(modes, text="Команды и примеры", command=self.show_help, bg=card, fg=fg, relief="flat").pack(side="right")
        tk.Label(self.root, text="1. Приложение или окно (выбор окна нужен только для нажатий)", bg=bg, fg=fg, font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=22, pady=(0, 6))
        window_row = tk.Frame(self.root, bg=bg); window_row.pack(fill="x", padx=22, pady=(0, 12))
        tk.Label(window_row, textvariable=self.target_name, anchor="w", bg=field, fg=fg,
                 padx=10, font=("Segoe UI", 10)).pack(side="left", fill="x", expand=True, ipady=9)
        tk.Button(window_row, text="Выбрать открытое окно", command=self.choose_window,
                  bg=accent, fg="white", relief="flat").pack(side="left", padx=(8, 0), ipady=5)
        tk.Label(self.root, text="Приложение или ярлык игры (.exe / .lnk / .url). Для Fortnite выбирайте ярлык Epic Games.", bg=bg, fg=c["muted"]).pack(anchor="w", padx=22, pady=(0, 5))
        game_row = tk.Frame(self.root, bg=bg); game_row.pack(fill="x", padx=22)
        style_input(tk.Entry(game_row, textvariable=self.game, font=("Segoe UI", 10)), c).pack(side="left", fill="x", expand=True, ipady=9)
        tk.Button(game_row, text="Выбрать файл / ярлык", command=self.choose, bg=card, fg=fg, relief="flat").pack(side="left", padx=(8, 0), ipady=5)
        tk.Label(self.root, text="2. Команды макроса (для простого запуска оставьте пустым)", bg=bg, fg=fg, font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=22, pady=(18, 6))
        self.prompt = style_input(tk.Text(self.root, height=6, wrap="word", padx=10, pady=10), c); self.prompt.pack(fill="x", padx=22)
        self.prompt.insert("1.0", "Например: нажми space; жди 1; нажми enter")
        self.prompt.bind("<FocusIn>", self._clear_prompt_example)
        buttons = tk.Frame(self.root, bg=bg); buttons.pack(fill="x", padx=22, pady=12)
        tk.Button(buttons, text="Проверить план", command=self.create, bg=accent, fg="white", relief="flat").pack(side="left", ipady=6)
        tk.Button(buttons, text="Выполнить", command=self.execute, bg=card, fg=fg, relief="flat").pack(side="left", padx=8, ipady=6)
        files = tk.Frame(self.root, bg=bg); files.pack(fill="x", padx=22, pady=(0, 10))
        style_input(tk.Entry(files, textvariable=self.scenario_name), c).pack(side="left", fill="x", expand=True, ipady=7)
        tk.Button(files, text="Открыть сценарий", command=self.add_scenario, bg=card, fg=fg, relief="flat").pack(side="left", padx=8, ipady=5)
        tk.Button(files, text="Сохранить как .jmacro", command=self.save_scenario, bg=card, fg=fg, relief="flat").pack(side="left", ipady=5)
        phrase_row = tk.Frame(self.root, bg=bg); phrase_row.pack(fill="x", padx=22, pady=(0, 12))
        tk.Label(phrase_row, text="Кодовая фраза", bg=bg, fg=fg, font=("Segoe UI", 10, "bold")).pack(side="left")
        style_input(tk.Entry(phrase_row, textvariable=self.code_phrase,
                             font=("Segoe UI", 10)), c).pack(side="left", fill="x", expand=True, padx=(12, 0), ipady=7)
        tk.Label(self.root, text="3. Проверенный план действий", bg=bg, fg=fg, font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=22, pady=(0, 6))
        self.preview = style_input(tk.Text(self.root, wrap="word", padx=10, pady=10), c); self.preview.pack(fill="both", expand=True, padx=22)
        tk.Label(self.root, textvariable=self.status, bg=bg, fg=accent).pack(anchor="w", padx=22, pady=12)

    def _clear_prompt_example(self, _event=None):
        if self.prompt.get("1.0", "end").strip().startswith("Например:"):
            self.prompt.delete("1.0", "end")

    def choose(self):
        path = filedialog.askopenfilename(title="Приложение или ярлык", filetypes=[("Приложения и ярлыки", "*.exe *.lnk *.url")])
        if path: self.game.set(path)

    def show_help(self):
        help_window = tk.Toplevel(self.root)
        help_window.title("Команды и примеры")
        help_window.geometry("710x540")
        c = self.colors
        field = tk.Text(help_window, wrap="word", bg=c["field"], fg=c["fg"], padx=16, pady=16)
        scroll = tk.Scrollbar(help_window, command=field.yview)
        scroll.pack(side="right", fill="y")
        field.configure(yscrollcommand=scroll.set)
        field.pack(fill="both", expand=True)
        field.insert("1.0", "ЗАПУСК ИГРЫ\n1. Выберите «Запустить приложение / игру».\n"
                     "2. Выберите EXE или ярлык игры. Окно и команды не нужны.\n"
                     "3. Задайте название и кодовую фразу, например: запусти фортнайт.\n"
                     "4. Нажмите «Сохранить как .jmacro».\n"
                     f"5. Скажите: {assistant_names()['jarvis']}, запусти фортнайт.\n\n"
                     "НАЖАТИЯ В ОКНЕ\nВыберите окно локальной игры и режим «Нажатия в окне».\n"
                     "Каждая команда — с новой строки или через точку с запятой.\n\n"
                     "нажми space — пробел\nнажми enter — Enter\nнажми ctrl+a — сочетание\n"
                     "жди 1.5 — пауза в секундах (до 30)\nудерживай right 2 — держать стрелку 2 секунды\n"
                     "курсор 100 200 — координаты на экране\nклик 100 200 — щелчок\n"
                     "текст Hello — ввод текста латиницей; кириллица пока не поддерживается\n\n"
                     "Клавиши: left, right, up, down, space, enter, esc, tab, backspace, delete, f1–f12, a–z, 0–9.\n"
                     "Пример: нажми space; жди 1; нажми enter\n\n"
                     "«Проверить план» ничего не нажимает. «Выполнить» запускает действия.\n"
                     "Чтобы остановить макрос, уведите мышь в левый верхний угол.\n"
                     "Макросы сетевых игр заблокированы; простой запуск разрешён.\n"
                     "«Открыть сценарий» загружает сохранённый файл. Изменения сохраняются кнопкой сохранения.")
        field.configure(state="disabled")

    def add_scenario(self):
        path = filedialog.askopenfilename(
            title="Добавить сценарий JARVIS",
            initialdir=str(SCENARIOS_DIR),
            filetypes=[("Сценарий JARVIS", "*.jmacro")],
        )
        if not path:
            return
        try:
            document = json.loads(Path(path).read_text(encoding="utf-8"))
            if document.get("формат") not in {"JARVIS-MACRO-1", "JARVIS-MACRO-2"}:
                raise ValueError("Это не сценарий JARVIS или его формат устарел.")
            self.scenario_type.set(document.get("тип", "macro"))
            self.plan = _validate(document.get("действия", []))
            self.prompt.delete("1.0", "end")
            self._imported_prompt = ""
            if not self.plan and self.scenario_type.get() != "launch":
                raise ValueError("В сценарии нет действий.")
            self.scenario_name.set(str(document.get("название", Path(path).stem)))
            self.code_phrase.set(str(document.get("кодовая_фраза", "")))
            self.game.set(str(document.get("файл", "")))
            saved_title = str(document.get("окно", "")).strip()
            if saved_title:
                self.target_name.set(saved_title)
            self._show(json.dumps(self.plan, ensure_ascii=False, indent=2), f"Сценарий добавлен: {self.scenario_name.get()}")
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            messagebox.showerror("Не удалось добавить сценарий", str(exc))

    def save_scenario(self):
        if not self.create():
            return
        SCENARIOS_DIR.mkdir(exist_ok=True)
        name = re.sub(r'[^\w\- ]+', "", self.scenario_name.get(), flags=re.UNICODE).strip() or "Новый сценарий"
        path = filedialog.asksaveasfilename(
            title="Сохранить сценарий JARVIS",
            initialdir=str(SCENARIOS_DIR),
            initialfile=f"{name}.jmacro",
            defaultextension=".jmacro",
            filetypes=[("Сценарий JARVIS", "*.jmacro")],
        )
        if not path:
            return
        phrase = normalize_phrase(self.code_phrase.get())
        document = {
            "формат": "JARVIS-MACRO-2",
            "тип": self.scenario_type.get(),
            "название": name,
            "кодовая_фраза": phrase,
            "окно": self.target_name.get() if self.target_name.get() != "Окно не выбрано" else "",
            "файл": self.game.get().strip(),
            "действия": self.plan,
        }
        try:
            Path(path).write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
            if phrase:
                save_phrase_binding(phrase, path)
                self.status.set(f"Сохранено. Фраза «{phrase}» привязана к сценарию")
            else:
                self.status.set(f"Сценарий сохранён: {Path(path).name}")
        except OSError as exc:
            messagebox.showerror("Не удалось сохранить сценарий", str(exc))

    def choose_window(self):
        c = self.colors
        picker = tk.Toplevel(self.root)
        picker.title("Выбор окна")
        picker.geometry("650x430")
        picker.configure(bg=c["bg"])
        picker.transient(self.root)
        picker.grab_set()
        try:
            picker.attributes("-alpha", 0.0)
        except tk.TclError:
            pass
        tk.Label(picker, text="В каком окне выполнять действия?", bg=c["bg"], fg=c["fg"],
                 font=("Segoe UI", 15, "bold")).pack(anchor="w", padx=18, pady=(18, 10))
        listing = tk.Listbox(picker, bg=c["field"], fg=c["fg"], selectbackground=c["accent"],
                             selectforeground="white", relief="flat", font=("Segoe UI", 10),
                             activestyle="none")
        listing.pack(fill="both", expand=True, padx=18)
        state = {"windows": []}

        def refresh():
            state["windows"] = visible_windows()
            listing.delete(0, "end")
            for _, title in state["windows"]:
                listing.insert("end", title)
            for index, (_, title) in enumerate(state["windows"]):
                if "a koopa's revenge 2" in title.casefold() or "adobe flash player 32" in title.casefold():
                    listing.selection_set(index)
                    listing.see(index)
                    break

        def accept(_event=None):
            selection = listing.curselection()
            if not selection:
                return
            self.target_hwnd, title = state["windows"][selection[0]]
            self.target_name.set(title)
            self.status.set(f"Выбрано окно: {title}")
            picker.destroy()

        controls = tk.Frame(picker, bg=c["bg"]); controls.pack(fill="x", padx=18, pady=14)
        tk.Button(controls, text="Обновить список", command=refresh, bg=c["card"], fg=c["fg"],
                  relief="flat").pack(side="left", ipady=5)
        tk.Button(controls, text="Выбрать", command=accept, bg=c["accent"], fg="white",
                  relief="flat").pack(side="right", ipadx=18, ipady=5)
        listing.bind("<Double-Button-1>", accept)
        refresh()

        def fade(alpha=0.0):
            try:
                picker.attributes("-alpha", min(1.0, alpha))
                if alpha < 1.0:
                    picker.after(16, fade, alpha + 0.12)
            except tk.TclError:
                pass
        fade()

    def create(self):
        try:
            if self.scenario_type.get() == "launch":
                path = Path(self.game.get().strip().strip('"'))
                if not path.is_file() or path.suffix.casefold() not in {".exe", ".lnk", ".url"}:
                    raise ValueError("Выберите существующее приложение или ярлык игры.")
                self.plan = []
                self._show(f"Запустить: {path}\nНажатия клавиш не выполняются.", "План запуска готов")
            else:
                prompt = self.prompt.get("1.0", "end").strip()
                if not (self.plan and prompt == getattr(self, "_imported_prompt", None)):
                    self.plan = explicit_plan(prompt)
                self._show(json.dumps(self.plan, ensure_ascii=False, indent=2), "План проверен")
            return True
        except (ValueError, OSError) as exc:
            messagebox.showerror("Ошибка плана", str(exc))
            return False

    def _legacy_model_plan(self):
        prompt = self.prompt.get("1.0", "end").strip().lower()
        if not prompt: return messagebox.showwarning("JARVIS", "Сначала опишите действия.")
        if any(marker in prompt for marker in ONLINE_MARKERS): return messagebox.showerror("Запрещено", "Макросы для онлайн-игр и сетевых приложений запрещены.")
        self.busy = True; self._pulse(0)
        def work():
            try:
                self.plan = make_plan(prompt); shown = json.dumps(self.plan, ensure_ascii=False, indent=2)
                self.root.after(0, lambda: self._show(shown, f"План готов: {len(self.plan)} действий"))
            except Exception as exc: self.root.after(0, lambda: self._failed(str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def _pulse(self, frame):
        if not self.busy: return
        self.status.set("Qwen составляет и проверяет план" + "." * (frame % 4))
        self.root.after(280, self._pulse, frame + 1)

    def _failed(self, error):
        self.busy = False; self.status.set("Не удалось создать план")
        messagebox.showerror("Ошибка плана", error)

    def _show(self, text, status):
        self.busy = False; self.preview.delete("1.0", "end"); self.preview.insert("1.0", text); self.status.set(status)

    def execute(self):
        if not self.create():
            return
        if self.scenario_type.get() == "launch":
            try:
                launch_application(self.game.get())
                self.status.set("Запуск приложения запрошен")
            except OSError as exc:
                messagebox.showerror("Ошибка запуска", str(exc))
            return
        game = Path(self.game.get())
        has_window = bool(self.target_hwnd and os.name == "nt" and ctypes.windll.user32.IsWindow(self.target_hwnd))
        has_game = game.is_file() and game.suffix.lower() == ".exe"
        if not has_window and not has_game:
            return messagebox.showwarning("JARVIS", "Выберите открытое окно или файл локальной игры .exe.")
        if not self.plan: return messagebox.showwarning("JARVIS", "Сначала создайте план.")
        target_text = self.target_name.get() if has_window else str(game)
        if any(marker in (target_text + " " + self.prompt.get("1.0", "end")).lower() for marker in ONLINE_MARKERS): return messagebox.showerror("Запрещено", "Обнаружена онлайн-игра или сетевое приложение.")
        self.status.set("Выполнение через 2 секунды. Для остановки уведите мышь в левый верхний угол.")
        def work():
            if has_window:
                activate_window(self.target_hwnd)
                time.sleep(2)
            else:
                os.startfile(str(game))
                time.sleep(3)
            run_actions(self.plan)
            self.root.after(0, lambda: self.status.set("Макрос завершён"))
        threading.Thread(target=work, daemon=True).start()

    def run(self): self.root.mainloop()


def run_saved_scenario(scenario_path):
    path = Path(scenario_path).resolve()
    if path.suffix.casefold() != ".jmacro" or not path.is_file():
        raise ValueError("Файл сценария не найден.")
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("формат") not in {"JARVIS-MACRO-1", "JARVIS-MACRO-2"}:
        raise ValueError("Неизвестный формат сценария.")
    if document.get("тип") == "launch":
        launch_application(document.get("файл", ""))
        return
    actions = _validate(document.get("действия", []))
    if not actions:
        raise ValueError("В сценарии нет действий.")

    title = str(document.get("окно", "")).strip()
    executable = Path(str(document.get("файл", "")).strip())
    target_hwnd = None
    if title:
        wanted = title.casefold()
        windows = visible_windows()
        exact = [item for item in windows if item[1].casefold() == wanted]
        partial = [item for item in windows if wanted in item[1].casefold() or item[1].casefold() in wanted]
        candidates = exact or partial
        if candidates:
            target_hwnd = candidates[0][0]

    target_text = f"{title} {executable}".casefold()
    if any(marker in target_text for marker in ONLINE_MARKERS):
        raise ValueError("Сценарий для сетевой игры заблокирован.")
    if target_hwnd:
        if not activate_window(target_hwnd):
            raise RuntimeError("Не удалось активировать сохранённое окно.")
        time.sleep(0.7)
    elif executable.is_file() and executable.suffix.casefold() == ".exe":
        os.startfile(str(executable))
        time.sleep(3)
    else:
        raise RuntimeError("Сохранённое окно не найдено, а запасной файл .exe не задан.")
    run_actions(actions)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", dest="scenario")
    parser.add_argument("--close", dest="close_scenario")
    arguments = parser.parse_args()
    if arguments.scenario:
        run_saved_scenario(arguments.scenario)
    elif arguments.close_scenario:
        close_saved_application(arguments.close_scenario)
    else:
        MacroWindow().run()

# JARVIS-ROUTER-v0.9.2-JARVIS-WORD-VARIANTS

import json
import re
import difflib
from assistant_identity import wake_aliases
from dataclasses import dataclass
from pathlib import Path

from discord_tools import parse_discord_voice_command
from stt_variants import read_dictionary, normalize_text as normalize_variant_text


ROUTER_CODE_VERSION = "JARVIS-ROUTER-v0.9.2-JARVIS-WORD-VARIANTS"
MACRO_PHRASES_FILE = Path(__file__).resolve().parent / "macro_phrases.json"
MACRO_DISABLED_FILE = Path(__file__).resolve().parent / "macro_disabled.json"
STT_VARIANTS_FILE = Path(__file__).resolve().parent / "stt_variants.json"


@dataclass
class Route:
    kind: str
    args: dict


class LocalRouter:
    # =========================================================
    # APPLICATION COMMANDS
    # =========================================================

    OPEN_WORDS = (
        "открой",
        "открывай",
        "откройте",
        "запусти",
        "запускай",
        "включи",
        "зайди",
        "open",
        "start",
        "launch",
    )

    HARD_CLOSE_WORDS = (
        "заверши процесс",
        "убей процесс",
        "выключи приложение",
        "закрой приложение полностью",
        "прибей процесс",
        "kill",
    )

    # =========================================================
    # WINDOWS
    # =========================================================

    WINDOW_CLOSE_WORDS = (
        "закрой",
        "закрой окно",
        "закрой это окно",
        "закрой активное окно",
        "закрой текущее окно",
    )

    MINIMIZE_WORDS = (
        "сверни",
        "свернуть",
        "минимизируй",
        "убери окно",
        "убери это окно",
        "убери активное окно",
    )

    MAXIMIZE_WORDS = (
        "разверни на весь экран",
        "развернуть на весь экран",
        "максимизируй",
        "на весь экран",
    )

    RESTORE_WORDS = (
        "разверни",
        "восстанови",
        "верни окно",
        "верни это окно",
    )

    FOCUS_WORDS = (
        "переключись на",
        "переключи на",
        "покажи",
        "выведи вперед",
        "выведи вперёд",
        "сделай активным",
        "сделай активной",
        "фокус на",
    )

    # =========================================================
    # STT NORMALIZATION
    # =========================================================

    STT_REPLACEMENTS = (
        # Common Whisper grammatical substitutions ("запасные словечки").
        (r"\b(?:открой|аткрой|открои|открой\s+ка|откройте|открыть|откроет|открою|открыл|открыла|открыли|открывай|открывает)\b", "открой"),
        (r"\b(?:запусти|запусти\s+ка|запустите|запускать|запускай|запускайте|запустить|запустит|запустил|запустила|запустили|запускает|пусти)\b", "запусти"),
        (r"\b(?:закрой|закрои|закрой\s+ка|закройте|закрыть|закроет|закрыл|закрыла|закрыли|закрывай|закрывает)\b", "закрой"),
        (r"\b(?:сверни|сверните|свернуть|свернет|свернул|свернула|сворачивает)\b", "сверни"),
        (r"\b(?:разверни|разверните|развернуть|развернет|развернул|развернула|разворачивает)\b", "разверни"),
        (r"\b(?:переключись|переключи|переключите|переключить|переключит|переключил|переключила)\b", "переключись"),
        (r"\b(?:нажми|нажми\s+ка|нажмите|нажать|нажмет|нажал|нажала|нажимает|жми)\b", "нажми"),
        (r"\b(?:напечатай|напечатайте|напечатать|напечатал|напечатала|напишет|напиши|печатай)\b", "напечатай"),
        (r"\b(?:введи|введите|ввести|введет|ввел|ввела|вставь|вставить)\b", "введи"),
        (r"\b(?:набери|наберите|набрать|набрал|набрала|наберет)\b", "набери"),
        (r"\b(?:найди|найдите|поищи|поищите|поискать|найти|найдет|отыщи)\b", "найди"),
        # JARVIS
        (r"\bжарвис\b", "джарвис"),
        (r"\b(?:джарви|жарви|джерви|жерви|джавис|жавис|джарвес|жарвес|джарвису|джарвиса|jarvi|jarvis)\b", "джарвис"),
        (r"\bджервис\b", "джарвис"),
        (r"\bжервис\b", "джарвис"),
        (r"\bджар\s+вис\b", "джарвис"),
        (r"\bжар\s+вис\b", "джарвис"),
        (r"\bджарвисе\b", "джарвис"),

        # Discord
        (r"\bдис\s*корт\b", "дискорд"),
        (r"\bдиск\s*орт\b", "дискорд"),
        (r"\bдиск\s*орды?\b", "дискорд"),
        (r"\bде\s*скотт\b", "дискорд"),
        (r"\bдискомфорт\b", "дискорд"),
        (r"\bдисконт\b", "дискорд"),
        (r"\bдисковод\b", "дискорд"),
        (r"\bесть\s+скоро\b", "дискорд"),

        # Discord kick / Vosk
        (r"\bкик\s+не\b", "кикни"),
        (r"\bкик\s+ни\b", "кикни"),
        (r"\bкикни\s+ка\b", "кикни"),
        (r"\bкик\s+не\b", "кик не"),
        (r"\bкик\s+ни\b", "кик не"),
        (r"\bкикни\s+ка\b", "кик ни"),
        
        # Dota
        (r"\b(?:дота|доту|доте|доты|дотой|дотан)\s*(?:2|два|ту)?\b", "дота"),
        (r"\bdota\s*(?:2|two)?\b", "дота"),

        # Apps
        (r"\bстимм?\b", "steam"),
        (r"\bютуб\b", "youtube"),
        (r"\bю\s*туб\b", "youtube"),
        (r"\bгугл\b", "google"),
        (r"\bгул\s+(?:хром|chrome)\b", "chrome"),
        (r"\bхром\b", "chrome"),
        (r"\bкром\b", "chrome"),
        (r"\bхрон\b", "chrome"),
        (r"\bгугл\s+хром\b", "chrome"),
        (r"\bопера\s+джи\s*икс\b", "opera gx"),
        (r"\bопера\s+джей\s*икс\b", "opera gx"),
        (r"\bопера\s+джиэкс\b", "opera gx"),
        (r"\bопера\s+гей\s*икс\b", "opera gx"),
        (r"\bоперу\b", "опера"),
        (r"\bмайкрософт\s+(?:эдж|эйдж|идж)\b", "edge"),
        (r"\bмикрософт\s+(?:эдж|эйдж|идж)\b", "edge"),
        (r"\b(?:эдж|эйдж|идж)\b", "edge"),
        (r"\bэн\s*видиа\b", "nvidia"),
        (r"\bн\s*видиа\b", "nvidia"),
        (r"\bэнвидиа\b", "nvidia"),
        (r"\bвс\s*код\b", "vscode"),
        (r"\bв\s*эс\s*код\b", "vscode"),

        # Qwen / Vosk
        (r"\bквенн\b", "квен"),
        (r"\bк вэн\b", "квен"),
        (r"\bк вен\b", "квен"),
        (r"\bкуэн\b", "квен"),
        (r"\bкуен\b", "квен"),
        (r"\bквн\s+а\b", "квен"),
        (r"\bквна\b", "квен"),
    )

    # =========================================================
    # APP ALIASES
    # =========================================================

    APP_ALIASES = {
        "chrome": "chrome",
        "google chrome": "chrome",
        "хром": "chrome",

        "opera gx": "opera_gx",
        "opera": "opera_gx",
        "опера gx": "opera_gx",
        "опера": "opera_gx",

        "microsoft edge": "edge",
        "edge": "edge",
        "майкрософт edge": "edge",
        "firefox": "firefox",
        "фаерфокс": "firefox",
        "brave": "brave",
        "брейв": "brave",
        "vivaldi": "vivaldi",
        "вивальди": "vivaldi",
        "yandex": "yandex",
        "яндекс": "yandex",
        "chromium": "chromium",
        "хромиум": "chromium",
        "браузер": "browser",
        "browser": "browser",

        "discord": "discord",
        "дискорд": "discord",
        "дс": "discord",

        "steam": "steam",
        "стим": "steam",

        "дота": "dota2",
        "дота 2": "dota2",
        "dota": "dota2",
        "dota2": "dota2",

        "soundpad": "soundpad",
        "саундпад": "soundpad",
        "саунд пад": "soundpad",
        "lossless scaling": "lossless_scaling",
        "лосслесс скейлинг": "lossless_scaling",
        "лослес скейлинг": "lossless_scaling",
        "counter strike 2": "cs2",
        "counter-strike 2": "cs2",
        "counter strike": "cs2",
        "контр страйк 2": "cs2",
        "кс 2": "cs2",
        "кс2": "cs2",

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

        "vscode": "vscode",
        "vs code": "vscode",
        "visual studio code": "vscode",
        "код": "vscode",

        "calculator": "calculator",
        "калькулятор": "calculator",

        "notepad": "notepad",
        "блокнот": "notepad",

        "explorer": "explorer",
        "проводник": "explorer",
    }

    BROWSER_ALIASES = {
        "opera gx": "opera_gx",
        "опера gx": "opera_gx",
        "опера": "opera_gx",
        "chrome": "chrome",
        "google chrome": "chrome",
        "хром": "chrome",
        "edge": "edge",
        "microsoft edge": "edge",
        "firefox": "firefox",
        "фаерфокс": "firefox",
        "brave": "brave",
        "брейв": "brave",
        "vivaldi": "vivaldi",
        "вивальди": "vivaldi",
        "yandex": "yandex",
        "яндекс": "yandex",
        "chromium": "chromium",
        "хромиум": "chromium",
        "майкрософт edge": "edge",
    }

    SYSTEM_TARGET_ALIASES = {
        "nvidia_control_panel": (
            "панель управления nvidia",
            "панель nvidia",
            "настройки nvidia",
        ),
        "control_panel": (
            "панель управления windows",
            "панель управления виндовс",
            "обычная панель управления",
            "панель управления",
        ),
        "sound_settings": (
            "настройки звука",
            "параметры звука",
        ),
        "display_settings": (
            "настройки экрана",
            "параметры экрана",
            "настройки дисплея",
        ),
        "bluetooth_settings": (
            "настройки bluetooth",
            "параметры bluetooth",
            "настройки блютуз",
            "параметры блютуз",
            "bluetooth",
            "блютуз",
        ),
        "windows_update": (
            "обновления windows",
            "обновление windows",
            "центр обновления",
            "windows update",
        ),
        "task_manager": (
            "диспетчер задач",
        ),
        "device_manager": (
            "диспетчер устройств",
        ),
        "disk_management": (
            "управление дисками",
            "диспетчер дисков",
        ),
        "network_connections": (
            "сетевые подключения",
            "сетевые соединения",
        ),
        "programs_features": (
            "программы и компоненты",
            "удаление программ",
        ),
        "services": (
            "службы windows",
            "службы виндовс",
            "службы",
        ),
        "power_options": (
            "параметры питания",
            "настройки питания",
            "электропитание",
        ),
        "settings": (
            "настройки windows",
            "настройки виндовс",
            "параметры windows",
            "параметры виндовс",
            "настройки",
            "параметры",
        ),
    }

    FOLDER_ALIASES = {
        "downloads": (
            "папку загрузки",
            "папка загрузки",
            "загрузки",
            "скачанные файлы",
        ),
        "documents": (
            "папку документы",
            "папка документы",
            "документы",
        ),
        "desktop": (
            "папку рабочего стола",
            "рабочий стол",
        ),
        "pictures": (
            "папку изображения",
            "папку картинки",
            "изображения",
            "картинки",
        ),
        "videos": (
            "папку видео",
            "видео",
        ),
        "music": (
            "папку музыка",
            "музыку",
            "музыка",
        ),
        "recycle_bin": (
            "корзину",
            "корзина",
        ),
        "project": (
            "папку джарвиса",
            "папку проекта",
            "проект джарвиса",
        ),
        "screenshots": (
            "папку скриншотов",
            "скриншоты",
        ),
    }

    # =========================================================
    # DISCORD BOT
    # =========================================================

    DISCORD_BOT_START = (
        "включи пятницу",
        "запусти пятницу",
        "запускай пятницу",
        "пятница включись",
        "включи бота",
        "запусти бота",
        "запускай бота",
        "включай бота",

        "включи бата",
        "запусти бата",
        "запускай бата",
        "включай бата",

        "включи пота",
        "запусти пота",
        "запускай пота",
        "включай пота",
    )

    DISCORD_BOT_STOP = (
        "выключи пятницу",
        "отключи пятницу",
        "останови пятницу",
        "пятница выключись",
        "выключи бота",
        "отключи бота",
        "останови бота",
        "выруби бота",

        "выключи бата",
        "отключи бата",
        "останови бата",
        "выруби бата",

        "выключи пота",
        "отключи пота",
        "останови пота",
        "выруби пота",
    )

    DISCORD_BOT_RESTART = (
        "перезапусти пятницу",
        "рестартни пятницу",
        "рестарт пятницы",
        "перезапусти бота",
        "рестартни бота",
        "рестарт бота",
        "перезапуск бота",

        "перезапусти бата",
        "рестартни бата",
        "рестарт бата",
        "перезапуск бата",

        "перезапусти пота",
        "рестартни пота",
        "рестарт пота",
        "перезапуск пота",
    )

    DISCORD_BOT_STATUS = (
        "пятница работает",
        "пятница включена",
        "пятница запущена",
        "статус пятницы",
        "проверь пятницу",
        "бот работает",
        "бот включен",
        "бот включён",
        "бот запущен",
        "статус бота",
        "проверь бота",
        "работает ли бот",
        "включен ли бот",
        "включён ли бот",
        "запущен ли бот",

        "бат работает",
        "бат включен",
        "бат включён",
        "бат запущен",
        "статус бата",
        "проверь бата",
        "работает ли бат",
        "включен ли бат",
        "включён ли бат",
        "запущен ли бат",

        "пот работает",
        "пот включен",
        "пот включён",
        "пот запущен",
        "статус пота",
        "проверь пота",
        "работает ли пот",
        "включен ли пот",
        "включён ли пот",
        "запущен ли пот",
    )

    # =========================================================
    # INIT
    # =========================================================

    def __init__(
        self,
        wake_words,
        tools,
    ):
        configured = [
            str(w).lower().strip()
            for w in wake_words
            if w
        ]

        self.wake_words = tuple(
            dict.fromkeys(
                configured
                + [
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
                    "джарвису",
                    "джарвиса",
                    "джар вис",
                    "жар вис",
                    "jarvis",
                    "jarvi",
                ]
            )
        )

        self.tools = tools

    # =========================================================
    # NORMALIZATION
    # =========================================================

    @staticmethod
    def norm(text):
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

    def normalize_stt(
        self,
        text,
    ):
        text = self.norm(text)

        for pattern, replacement in self.STT_REPLACEMENTS:
            text = re.sub(
                pattern,
                replacement,
                text,
            )

        # User-selected real word forms are an extra layer after the built-in
        # ASR fixes. Replacement is boundary-aware; substrings are untouched.
        text = normalize_variant_text(text, read_dictionary(STT_VARIANTS_FILE))

        text = self.norm(text)

        # Small typo-tolerance layer for command vocabulary.  It deliberately
        # only touches known control words, so application names and arguments
        # are left unchanged (e.g. "настроки" -> "настройки").
        command_words = {
            "настройки", "настройку", "настройках", "настроек", "настройка",
            "приложение", "приложения", "приложению", "приложений",
            "браузер", "браузера", "браузере", "браузеру",
            "громкость", "громкости", "громче", "тише",
            "микрофон", "микрофона", "микрофоне", "микрофону", "микро",
            "динамики", "динамиков", "динамик",
            "помощь", "помоги", "помощи",
            "журнал", "журнала", "журнале",
            "команды", "команда", "команду", "команд",
            "выключись", "выключи", "выключиться", "выключение", "останови",
            "отключись", "отключи", "отключение",
            "перезапусти", "перезапуск", "перезапустить", "перезапускай",
            "поставь", "поставить", "установи", "установить", "установка",
            "русская", "русский", "русскую",
            "рулетка", "рулетку", "рулетке",
            "слушай", "слушать", "слушаю", "молчи", "молчать",
            "разреши", "разрешить",
            "запусти", "запустить", "запуск",
            "открой", "открыть", "открывай",
            "закрой", "закрыть", "закрывай",
            "сверни", "свернуть", "разверни", "развернуть",
            "покажи", "показать", "найди", "найти", "поиск",
            "скажи", "сказать", "озвучь", "озвучить", "повтори", "повторить",
            "дота", "доту", "доте", "доты", "дотой", "дото", "дот",
        }
        corrected = []
        for word in text.split():
            if len(word) >= 5 and word not in command_words:
                match = difflib.get_close_matches(word, command_words, n=1, cutoff=0.78)
                if match and abs(len(match[0]) - len(word)) <= 2:
                    word = match[0]
            corrected.append(word)
        return " ".join(corrected)

    # =========================================================
    # REMOVE WAKE WORD
    # =========================================================

    def strip_wake(
        self,
        text,
    ):
        text = self.normalize_stt(
            text
        )

        for wake in sorted(
            wake_aliases("jarvis", self.wake_words),
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

            before = text[:match.start()].strip()
            after = text[match.end():].strip()

            cleaned = " ".join(
                part
                for part in (
                    before,
                    after,
                )
                if part
            )

            return self.normalize_stt(
                cleaned
            )

        # STT may distort the assistant name so strongly that an exact
        # alias is impossible ("джарлиз", "жаровиз", etc.).  Try a close
        # match only at the beginning of the phrase, where the wake word is
        # expected; this avoids changing ordinary command arguments.
        words = text.split()
        if words:
            aliases = wake_aliases("jarvis", self.wake_words)
            candidate = words[0]
            close = difflib.get_close_matches(candidate, aliases, n=1, cutoff=0.62)
            if close and abs(len(close[0]) - len(candidate)) <= 3:
                return self.normalize_stt(" ".join(words[1:]))

        return text

    # =========================================================
    # EXPLICIT QWEN
    # =========================================================

    def _extract_qwen_request(
        self,
        text,
    ):
        """
        Qwen запускается ТОЛЬКО при явном вызове.

        Голос:
            спроси квена почему небо синее
            спроси квен почему небо синее
            квен расскажи про pci express

        Клавиатура:
            q: почему небо синее
            q почему небо синее

        Возвращает:
            текст запроса -> если Qwen вызван явно
            None         -> если это обычная команда JARVIS
        """

        t = self.normalize_stt(
            text
        )

        # -----------------------------------------------------
        # Keyboard shortcut:
        #
        # q: вопрос
        #
        # norm() превращает ":" в пробел,
        # поэтому здесь остаётся "q вопрос".
        # -----------------------------------------------------

        match = re.match(
            r"^q\s+(.+)$",
            t,
            flags=re.IGNORECASE,
        )

        if match:
            query = match.group(1).strip()

            if query:
                return query

        # -----------------------------------------------------
        # "спроси квена ..."
        # -----------------------------------------------------

        patterns = (
            r"^спроси\s+квена?\s+(.+)$",
            r"^спроси\s+у\s+квена?\s+(.+)$",
            r"^спроси\s+qwen\s+(.+)$",

            r"^квен\s+(.+)$",
            r"^qwen\s+(.+)$",

            r"^передай\s+квену\s+(.+)$",
            r"^скажи\s+квену\s+(.+)$",
        )

        for pattern in patterns:
            match = re.match(
                pattern,
                t,
                flags=re.IGNORECASE,
            )

            if not match:
                continue

            query = match.group(1).strip()

            if query:
                return query

        # -----------------------------------------------------
        # Qwen вызван, но вопрос не сказан.
        # Специальная строка-сигнал.
        # -----------------------------------------------------

        if t in {
            "спроси квена",
            "спроси квен",
            "спроси у квена",
            "квен",
            "qwen",
        }:
            return ""

        return None

    # =========================================================
    # KNOWN APP
    # =========================================================

    def _known_app(
        self,
        text,
    ):
        t = self.norm(
            text
        )

        for alias in sorted(
            self.APP_ALIASES,
            key=len,
            reverse=True,
        ):
            if re.search(
                rf"(?<!\w){re.escape(alias)}(?!\w)",
                t,
            ):
                return self.APP_ALIASES[
                    alias
                ]

        return (
            self.tools
            .known_app_from_text(
                t
            )
        )

    def browser_from_text(
        self,
        text,
    ):
        """Возвращает конкретный браузер, не считая общего слова."""

        t = self.normalize_stt(
            text
        )

        for alias in sorted(
            self.BROWSER_ALIASES,
            key=len,
            reverse=True,
        ):
            if re.search(
                rf"(?<!\w){re.escape(alias)}(?!\w)",
                t,
            ):
                return self.BROWSER_ALIASES[
                    alias
                ]

        return None

    def _mapped_phrase(
        self,
        text,
        mapping,
    ):
        t = self.normalize_stt(
            text
        )

        candidates = []

        for target, aliases in mapping.items():
            for alias in aliases:
                candidates.append(
                    (
                        len(alias),
                        target,
                        alias,
                    )
                )

        candidates.sort(
            reverse=True
        )

        for _, target, alias in candidates:
            if re.search(
                rf"(?<!\w){re.escape(alias)}(?!\w)",
                t,
            ):
                return target

        return None

    # =========================================================
    # ACTIVE WINDOW
    # =========================================================

    def _asks_active_window(
        self,
        text,
    ):
        t = self.norm(
            text
        )

        direct_phrases = (
            "какое окно активно",
            "какое окно сейчас активно",
            "какой окно активно",
            "какой окно сейчас активно",
            "какая окно активно",
            "какая окно сейчас активно",

            "назови активное окно",
            "скажи активное окно",

            "что сейчас активно",
            "что у меня активно",
            "что сейчас у меня активно",

            "что за окно",
            "что за окно сейчас",
            "что за окно открыто",

            "какое активное окно",
            "какой активное окно",
        )

        if any(
            phrase in t
            for phrase in direct_phrases
        ):
            return True

        has_window = (
            "окно" in t
        )

        has_active = any(
            word in t
            for word in (
                "активно",
                "активное",
                "активный",
                "активна",
                "активным",
            )
        )

        if (
            has_window
            and has_active
        ):
            return True

        words = set(
            t.split()
        )

        has_question = bool(
            words.intersection(
                {
                    "что",
                    "какое",
                    "какой",
                    "какая",
                }
            )
        )

        return (
            has_question
            and has_active
        )

    # =========================================================
    # WINDOW TARGET
    # =========================================================

    def _window_target(
        self,
        text,
    ):
        t = self.norm(
            text
        )

        if any(
            phrase in t
            for phrase in (
                "это окно",
                "активное окно",
                "активный окно",
                "текущее окно",
                "текущий окно",
                "окно сейчас",
            )
        ):
            return "active"

        app = self._known_app(
            t
        )

        if app:
            return app

        system_target = self._mapped_phrase(t, self.SYSTEM_TARGET_ALIASES)
        if system_target:
            return system_target

        return "active"

    # =========================================================
    # ROUTER
    # =========================================================

    def macro_for_phrase(self, text):
        try:
            registry = json.loads(MACRO_PHRASES_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None
        if not isinstance(registry, dict):
            return None
        wanted = self.normalize_stt(" ".join(str(text or "").casefold().replace("ё", "е").split()))
        try:
            disabled = json.loads(MACRO_DISABLED_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            disabled = []
        disabled_normalized = {self.normalize_stt(item) for item in disabled if isinstance(item, str)}
        if wanted in disabled_normalized:
            return None
        normalized_registry = {self.normalize_stt(key): value for key, value in registry.items() if isinstance(key, str)}
        scenario = normalized_registry.get(wanted)
        operation = "run"
        if not scenario:
            words = wanted.split()
            if words and words[0] in {"открой", "запусти"}:
                other = "запусти" if words[0] == "открой" else "открой"
                scenario = normalized_registry.get(" ".join([other] + words[1:]))
            elif words and words[0] == "закрой":
                # A launch command automatically gets a safe inverse command:
                # "открой/запусти X" -> "закрой X".
                for verb in ("открой", "запусти"):
                    candidate = normalized_registry.get(" ".join([verb] + words[1:]))
                    if candidate:
                        scenario = candidate
                        operation = "close"
                        break
        if not scenario:
            return None
        path = Path(str(scenario)).resolve()
        if not path.is_file() or path.suffix.casefold() != ".jmacro":
            return None
        if operation == "close":
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                return None
            if document.get("тип") != "launch":
                return None
        return str(path), operation

    def route(
        self,
        text,
    ):
        normalized = self.normalize_stt(
            text
        )

        # Protect assistant-stop phrases before strip_wake removes the name.
        # This makes "закрой Джарвиса" an assistant command, never a window
        # close or computer power command.
        stop_actions = ("выключи", "закрой", "останови")
        assistant_names = tuple(dict.fromkeys(wake_aliases("jarvis", self.wake_words) + self.wake_words))
        if any(normalized == action + " " + name for action in stop_actions for name in assistant_names):
            return Route("exit", {})

        t = self.strip_wake(
            normalized
        )

        t = self.normalize_stt(
            t
        )

        if not t:
            return Route(
                "empty",
                {},
            )

        # =====================================================
        # EXPLICIT QWEN
        #
        # Очень важно:
        # Qwen больше НЕ является fallback.
        # =====================================================

        qwen_request = self._extract_qwen_request(
            t
        )

        if qwen_request is not None:
            if not qwen_request:
                return Route(
                    "qwen_empty",
                    {},
                )

            return Route(
                "llm",
                {
                    "text": qwen_request,
                },
            )

        # Computer power commands are intentionally exact. Phrases naming the
        # assistant are handled by FULL EXIT below and can never reach these.
        if t in {
            "выключи компьютер", "выключи комп", "выключи пк",
            "выключи компа", "выключить компьютер", "выключить комп", "выключить пк",
            "отключи компьютер", "отключи комп", "отключи пк",
            "выруби компьютер", "выруби комп", "выруби пк",
            "заверши работу компьютера", "заверши работу пк",
        }:
            return Route("computer_shutdown", {})

        if t in {
            "перезагрузи компьютер", "перезагрузи комп", "перезагрузи пк",
            "перезагрузи компа", "перезагрузить компьютер", "перезагрузить комп", "перезагрузить пк",
            "перезагрузка компьютер", "перезагрузка комп", "перезагрузка пк",
            "перезапусти компьютер", "перезапусти комп", "перезапусти пк",
            "перезагрузка компьютера", "перезагрузка компа", "перезагрузка пк",
        }:
            return Route("computer_restart", {})

        # A phrase explicitly created by the owner has priority over built-in
        # commands. This lets the constructor redefine even ordinary wording.
        macro_match = self.macro_for_phrase(t)
        if macro_match:
            macro_path, macro_operation = macro_match
            return Route("macro_close" if macro_operation == "close" else "macro_phrase", {"path": macro_path})

        # =====================================================
        # PASSIVE SLEEP
        # =====================================================

        if t in {
            "замолчи",
            "спать",
            "иди спать",
            "уходи спать",
            "уйди в ожидание",
            "режим ожидания",
        }:
            return Route(
                "sleep",
                {},
            )

        # =====================================================
        # FULL EXIT
        # =====================================================

        if t in {
            "выключись",
            "отключись",
            "завершить работу",
            "заверши работу",
            "полностью выключись",
            "полностью отключись",
            "выключи джарвиса",
            "закрой джарвиса",
            "останови джарвиса",
            "заверши джарвиса",
            "джарвис выключись",
            "джарвис отключись",
            "exit",
            "quit",
        }:
            return Route(
                "exit",
                {},
            )

        # =====================================================
        # HELP
        # =====================================================

        if t in {
            "помощь",
            "help",
            "/help",
            "покажи помощь",
            "покажи список возможностей",
            "список возможностей",
            "что умеет джарвис",
            "что ты умеешь",
        }:
            return Route(
                "help",
                {},
            )

        # =====================================================
        # DISCORD BOT — START
        # =====================================================

        if t in self.DISCORD_BOT_START:
            return Route(
                "discord_bot_start",
                {},
            )

        # =====================================================
        # DISCORD BOT — STOP
        # =====================================================

        if t in self.DISCORD_BOT_STOP:
            return Route(
                "discord_bot_stop",
                {},
            )

        # =====================================================
        # DISCORD BOT — RESTART
        # =====================================================

        if t in self.DISCORD_BOT_RESTART:
            return Route(
                "discord_bot_restart",
                {},
            )

        # =====================================================
        # DISCORD BOT — STATUS
        # =====================================================

        if t in self.DISCORD_BOT_STATUS:
            return Route(
                "discord_bot_status",
                {},
            )

        # =====================================================
        # DISCORD VOICE
        # =====================================================

        discord_command = (
            parse_discord_voice_command(
                t
            )
        )

        if discord_command is not None:
            return Route(
                "discord_voice",
                {
                    "text": t,
                },
            )

        # =====================================================
        # WINDOWS SYSTEM PAGES / TOOLS
        # =====================================================

        if any(
            word in t
            for word in self.OPEN_WORDS
        ):
            system_target = self._mapped_phrase(
                t,
                self.SYSTEM_TARGET_ALIASES,
            )

            if system_target:
                return Route(
                    "open_system",
                    {
                        "target": system_target,
                    },
                )

            folder_target = self._mapped_phrase(
                t,
                self.FOLDER_ALIASES,
            )

            if folder_target:
                return Route(
                    "open_folder",
                    {
                        "target": folder_target,
                    },
                )

        # =====================================================
        # ACTIVE WINDOW
        # =====================================================

        if self._asks_active_window(
            t
        ):
            return Route(
                "get_active_window",
                {},
            )

        if any(phrase in t for phrase in (
            "назови открытые окна",
            "перечисли открытые окна",
            "какие окна открыты",
            "список открытых окон",
        )):
            return Route("list_windows", {})

        search_match = re.match(
            r"^(?:найди\s+(?:в\s+)?(?:гугле|google)|загугли)\s+(.+)$",
            t,
        )
        if search_match:
            return Route("browser_search", {"query": search_match.group(1).strip(), "browser": "chrome"})

        key_match = re.match(
            r"^нажми\s+(?:на\s+)?(?:клавишу\s+|кнопку\s+)?"
            r"(пробел|спейс|space|энтер|ентер|enter|ввод|эскейп|эск|escape|esc|таб|tab|"
            r"стрелку?\s+(?:вверх|вниз|влево|вправо)|вверх|вниз|влево|вправо|бэкспейс|backspace|делит|delete)$",
            t,
        )
        if key_match:
            return Route("press_key", {"key": key_match.group(1).replace("стрелку", "стрелка")})

        type_match = re.match(
            r"^(?:напечатай|введи|впиши|набери)\s+(?:текст\s+)?(.+)$",
            t,
        )
        if type_match:
            return Route("type_text", {"text": type_match.group(1).strip()})

        if any(phrase in t for phrase in (
            "играй в игру с яблоками",
            "начни отбивать яблоки",
            "играй в яблоки",
            "запусти контроллер яблок",
        )):
            return Route("apple_game_start", {})

        if any(phrase in t for phrase in (
            "останови игру с яблоками",
            "перестань отбивать яблоки",
            "останови контроллер яблок",
            "хватит играть в яблоки",
        )):
            return Route("apple_game_stop", {})

        if (
            "дота" in t
            and (
                "поиск игр" in t
                or "найди игр" in t
                or "нажми играть" in t
            )
        ):
            return Route("dota_match_search", {})

        color_match = re.search(
            r"\bнажми\s+(?:на\s+)?(?:самую\s+)?(зел[её]ную|синюю)\s+кнопку\b",
            t,
        )
        if color_match:
            return Route(
                "click_colored_button",
                {"color": color_match.group(1), "target": "active"},
            )

        click_match = re.search(
            r"\bнажми\s+(?:на\s+)?(?:кнопку\s+)?(.+)$",
            t,
        )
        if click_match:
            return Route(
                "click_ui_element",
                {"label": click_match.group(1).strip()},
            )

        # =====================================================
        # MINIMIZE
        # =====================================================

        if any(
            phrase in t
            for phrase in self.MINIMIZE_WORDS
        ):
            return Route(
                "minimize_window",
                {
                    "target":
                        self._window_target(
                            t
                        ),
                },
            )

        # =====================================================
        # MAXIMIZE
        # =====================================================

        if any(
            phrase in t
            for phrase in self.MAXIMIZE_WORDS
        ):
            return Route(
                "maximize_window",
                {
                    "target":
                        self._window_target(
                            t
                        ),
                },
            )

        # =====================================================
        # RESTORE
        # =====================================================

        if any(
            phrase in t
            for phrase in self.RESTORE_WORDS
        ):
            if (
                "на весь экран"
                not in t
            ):
                return Route(
                    "restore_window",
                    {
                        "target":
                            self._window_target(
                                t
                            ),
                    },
                )

        # =====================================================
        # FOCUS
        # =====================================================

        if any(
            phrase in t
            for phrase in self.FOCUS_WORDS
        ):
            app = self._known_app(
                t
            )

            if app:
                return Route(
                    "focus_window",
                    {
                        "target": app,
                    },
                )

        # =====================================================
        # HARD CLOSE APP
        # =====================================================

        if any(
            phrase in t
            for phrase in self.HARD_CLOSE_WORDS
        ):
            app = self._known_app(
                t
            )

            if app and app != "browser":
                return Route(
                    "close_app",
                    {
                        "app": app,
                    },
                )

        # =====================================================
        # CLOSE WINDOW
        # =====================================================

        if any(
            phrase in t
            for phrase in self.WINDOW_CLOSE_WORDS
        ):
            return Route(
                "close_window",
                {
                    "target":
                        self._window_target(
                            t
                        ),
                },
            )

        # =====================================================
        # SCREENSHOT
        # =====================================================

        if any(
            phrase in t
            for phrase in (
                "скриншот",
                "сделай скрин",
                "сделай скриншот",
                "сними экран",
                "снимок экрана",
            )
        ):
            return Route(
                "screenshot",
                {},
            )

        # =====================================================
        # TIME
        # =====================================================

        if any(
            phrase in t
            for phrase in (
                "который час",
                "сколько времени",
                "скажи время",
                "время сейчас",
                "какое время",
            )
        ):
            return Route(
                "time",
                {},
            )

        # =====================================================
        # VOLUME
        # =====================================================

        if any(
            word in t
            for word in (
                "громкость",
                "volume",
            )
        ):
            match = re.search(
                r"(?<!\d)(100|\d{1,2})(?!\d)",
                t,
            )

            if match and (
                t.strip().startswith(("громкость", "volume"))
                or any(
                    phrase in t
                    for phrase in (
                        "постав",
                        "сдел",
                        "установ",
                        "на ",
                    )
                )
            ):
                return Route(
                    "volume",
                    {
                        "value":
                            int(
                                match.group(1)
                            ),
                    },
                )

        # =====================================================
        # OPEN APP
        # =====================================================

        app = self._known_app(
            t
        )

        if app:
            if any(
                word in t
                for word in self.OPEN_WORDS
            ):
                if app == "browser":
                    if (
                        "по умолчанию" in t
                        or "основной браузер" in t
                    ):
                        return Route(
                            "browser_default",
                            {},
                        )

                    return Route(
                        "browser_request",
                        {},
                    )

                return Route(
                    "open_app",
                    {
                        "app": app,
                    },
                )

        # =====================================================
        # WEBSITES
        # =====================================================

        sites = {
            "youtube":
                "https://youtube.com",

            "google":
                "https://google.com",
        }

        if any(
            word in t
            for word in self.OPEN_WORDS
        ):
            for alias, url in sites.items():
                if alias in t:
                    return Route(
                        "open_url",
                        {
                            "url": url,
                        },
                    )

        # Повторение произвольной короткой фразы голосом JARVIS. Специальные
        # команды вроде «скажи время» уже обработаны выше и сюда не попадут.
        repeat_match = re.match(
            r"^(?:скажи|скажи\s+ка|повтори|повтори\s+ка|произнеси|озвучь)\s+(.+)$",
            t,
        )
        if repeat_match:
            return Route("say", {"text": repeat_match.group(1).strip()[:500]})

        # =====================================================
        # UNKNOWN
        #
        # КЛЮЧЕВОЕ ИЗМЕНЕНИЕ v0.7.7:
        #
        # Раньше:
        # неизвестное -> Qwen
        #
        # Теперь:
        # неизвестное -> unknown
        #
        # Qwen вообще не запускается.
        # =====================================================

        return Route(
            "unknown",
            {
                "text": t,
            },
        )

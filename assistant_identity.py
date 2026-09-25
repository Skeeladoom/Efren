"""Shared, live assistant names for the panel and voice processes."""
import json
import os
import re
import sys
from pathlib import Path

BASE_DIR = Path(sys.executable).resolve().parent.parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
NAMES_FILE = BASE_DIR / "assistant_names.json"
DEFAULT_NAMES = {"friday": "Пятница", "jarvis": "Джарвис"}
_signature = None
_names = DEFAULT_NAMES.copy()


def names():
    global _signature, _names
    try:
        signature = NAMES_FILE.stat().st_mtime_ns
        if signature != _signature:
            data = json.loads(NAMES_FILE.read_text(encoding="utf-8"))
            updated = DEFAULT_NAMES.copy()
            for key in updated:
                value = data.get(key)
                if isinstance(value, str) and re.fullmatch(r"[а-яА-ЯёЁa-zA-Z]+(?:[ -][а-яА-ЯёЁa-zA-Z]+)*", value) and len(value) <= 32:
                    updated[key] = value
            _names, _signature = updated, signature
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return _names.copy()


def normalize_name(value):
    return " ".join(value.casefold().replace("ё", "е").replace("-", " ").split())


def custom_wake(key):
    value = normalize_name(names()[key])
    return value if value != normalize_name(DEFAULT_NAMES[key]) else ""


def wake_aliases(key, defaults):
    custom = custom_wake(key)
    return (custom,) if custom else defaults


def save_name(key, value):
    global _signature, _names
    value = value.strip()
    if not re.fullmatch(r"[а-яА-ЯёЁa-zA-Z]+(?:[ -][а-яА-ЯёЁa-zA-Z]+)*", value) or len(value) > 32:
        raise ValueError("Имя: от 1 до 32 букв, допустимы пробелы и дефис.")
    data = names()
    other = "jarvis" if key == "friday" else "friday"
    if normalize_name(value) == normalize_name(data[other]):
        raise ValueError("У помощников должны быть разные имена.")
    data[key] = value
    temporary = NAMES_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, NAMES_FILE)
    _names = data
    _signature = None


def display_names(text):
    text = str(text)
    if not re.search(r"jarvis|джарвис|пятниц", text, re.IGNORECASE):
        return text
    current = names()
    text = re.sub(r"\b(?:jarvis|джарвис[ауе]?)\b", lambda _: current["jarvis"], text, flags=re.IGNORECASE)
    return re.sub(r"\bпятниц[ауыей]+\b", lambda _: current["friday"], text, flags=re.IGNORECASE)

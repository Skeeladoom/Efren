"""Local morphology-backed recognition dictionary shared by panel and router."""
import json
import os
import re
from pathlib import Path

WORD_RE = re.compile(r"^[A-Za-zА-Яа-яЁё-]{2,80}$")
CASES = {"nomn", "gent", "datv", "accs", "ablt", "loct"}


def normalize_word(value):
    return str(value or "").strip().casefold().replace("ё", "е")


def generate_forms(word):
    source = str(word or "").strip()
    normalized = normalize_word(source)
    if not WORD_RE.fullmatch(source) or " " in source:
        raise ValueError("Введите одно слово длиной от 2 до 80 символов.")
    try:
        import pymorphy3
    except ImportError as exc:
        raise RuntimeError("Компонент pymorphy3 не установлен в runtime Lite.") from exc
    parsed = pymorphy3.MorphAnalyzer().parse(normalized)
    if not parsed:
        return [normalized]
    forms = []
    for item in parsed[0].lexeme:
        form = normalize_word(item.word)
        if "sing" in item.tag and item.tag.case in CASES and form not in forms:
            forms.append(form)
    forms = forms or [normalized]
    return [value[:1].upper() + value[1:] for value in forms] if source[:1].isupper() else forms


def read_dictionary(path):
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError, TypeError):
        return {}
    result = {}
    if isinstance(raw, dict):
        for canonical, values in raw.items():
            canonical = normalize_word(canonical)
            if not canonical or not isinstance(values, list):
                continue
            clean = []
            for value in values:
                value = normalize_word(value)
                if value and value not in clean:
                    clean.append(value)
            if clean:
                result[canonical] = clean
    return result


def save_selected(path, canonical, selected):
    path = Path(path)
    canonical = normalize_word(canonical)
    values = []
    for value in selected or []:
        value = normalize_word(value)
        if value and value not in values:
            values.append(value)
    if not canonical or not values:
        raise ValueError("Выберите хотя бы одну словоформу.")
    data = read_dictionary(path)
    data[canonical] = values
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return data


def normalize_text(text, dictionary):
    lookup = {}
    for canonical, variants in dictionary.items():
        for variant in variants:
            lookup[normalize_word(variant)] = normalize_word(canonical)
    if not lookup:
        return text
    pattern = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(x) for x in sorted(lookup, key=len, reverse=True)) + r")(?!\w)", re.IGNORECASE)
    return pattern.sub(lambda match: lookup.get(normalize_word(match.group(0)), match.group(0)), text)

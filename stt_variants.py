"""Local morphology-backed recognition dictionary shared by panel and router."""
import json
import os
import re
import hashlib
import itertools
from pathlib import Path

WORD_RE = re.compile(r"^[A-Za-zА-Яа-яЁё-]{2,80}$")
CASES = {"nomn", "gent", "datv", "accs", "ablt", "loct"}
_morph_analyzer = None
_auto_cache = {}


def normalize_word(value):
    return str(value or "").strip().casefold().replace("ё", "е")


def generate_forms(word):
    source = str(word or "").strip()
    normalized = normalize_word(source)
    if not WORD_RE.fullmatch(source) or " " in source:
        raise ValueError("Введите одно слово длиной от 2 до 80 символов.")
    parsed = _morph().parse(normalized)
    if not parsed:
        return [normalized]
    forms = []
    for item in parsed[0].lexeme:
        form = normalize_word(item.word)
        if "sing" in item.tag and item.tag.case in CASES and form not in forms:
            forms.append(form)
    forms = forms or [normalized]
    return [value[:1].upper() + value[1:] for value in forms] if source[:1].isupper() else forms


def _morph():
    global _morph_analyzer
    if _morph_analyzer is None:
        try:
            import pymorphy3
        except ImportError as exc:
            raise RuntimeError("Компонент pymorphy3 не установлен в runtime Lite.") from exc
        _morph_analyzer = pymorphy3.MorphAnalyzer()
    return _morph_analyzer


def generate_all_forms(word):
    """Generate real pymorphy lexemes for automatic command normalization."""
    normalized = normalize_word(word)
    if not WORD_RE.fullmatch(normalized) or " " in normalized:
        return []
    parsed = _morph().parse(normalized)
    forms = [normalized]
    if parsed:
        for item in parsed[0].lexeme:
            form = normalize_word(item.word)
            if WORD_RE.fullmatch(form) and form not in forms:
                forms.append(form)
    return forms[:96]


def generate_phrase_forms(phrase, limit=128):
    """Inflect every word of an assistant name, including multi-word names."""
    parts = [part for part in re.findall(r"[A-Za-zА-Яа-яЁё-]{2,80}", str(phrase or ""))]
    if not parts:
        return []
    groups = [generate_all_forms(part) or [normalize_word(part)] for part in parts]
    result = []
    for combination in itertools.product(*groups):
        value = " ".join(combination)
        if value not in result:
            result.append(value)
        if len(result) >= limit:
            break
    return result


def ensure_auto_dictionary(path, words):
    """Persist/reuse morphology for the current built-in and user commands."""
    path = Path(path)
    clean_words = sorted({normalize_word(word) for word in words if WORD_RE.fullmatch(normalize_word(word))})
    # Include the collector format version so an older oversized cache is
    # rebuilt even when the resulting source word set happens to be unchanged.
    digest = hashlib.sha256(("collector-v3\n" + "\n".join(clean_words)).encode("utf-8")).hexdigest()
    cache_key = str(path.resolve())
    cached = _auto_cache.get(cache_key)
    if cached and cached[0] == digest:
        return cached[1]

    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (FileNotFoundError, OSError, ValueError, TypeError):
        raw = {}
    if isinstance(raw, dict) and raw.get("_source_hash") == digest:
        result = read_dictionary(path)
        _auto_cache[cache_key] = (digest, result)
        return result

    result = {}
    for canonical in clean_words:
        try:
            forms = generate_all_forms(canonical)
        except RuntimeError:
            return {}
        if forms:
            result[canonical] = forms
    document = {"_source_hash": digest, **result}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    # This is a generated cache, not a user-edited dictionary. Keep it compact
    # so hundreds of lexemes do not turn into tens of thousands of text lines.
    temporary.write_text(
        json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)
    _auto_cache[cache_key] = (digest, result)
    return result


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
    # A word that is itself a registered command token must never be changed
    # merely because it is also a grammatical form of another token.
    for canonical in dictionary:
        lookup[normalize_word(canonical)] = normalize_word(canonical)
    if not lookup:
        return text
    pattern = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(x) for x in sorted(lookup, key=len, reverse=True)) + r")(?!\w)", re.IGNORECASE)
    return pattern.sub(lambda match: lookup.get(normalize_word(match.group(0)), match.group(0)), text)

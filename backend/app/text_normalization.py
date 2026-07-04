from __future__ import annotations

import re
from typing import Any

MOJIBAKE_MARKERS = ("\u00d0", "\u00d1", "\u00c2", "\ufffd")
TECHNICAL_TOKEN_RE = re.compile(r"^[A-Z][A-Z0-9_:/.-]{2,}$")
URL_OR_DOI_RE = re.compile(r"^(https?://|doi:|10\.)", re.IGNORECASE)
PROTECTED_TEXT_KEYS = {"url", "doi", "patent_number", "license"}


def repair_text(value: str) -> str:
    if not value or _is_technical_token(value) or _is_url_or_doi(value):
        return value
    best = value
    for _ in range(4):
        candidates = {_repair_utf8_misdecoded(best), _repair_mixed_cp1251_latin1(best), _repair_utf16_lowbyte(best), best}
        next_best = min(candidates, key=_badness)
        if next_best == best:
            break
        best = next_best
    return best


def repair_payload(value: Any) -> Any:
    return _repair_payload(value)


def _repair_payload(value: Any, key: str | None = None) -> Any:
    if isinstance(value, str):
        if key and key.lower() in PROTECTED_TEXT_KEYS:
            return value
        return repair_text(value)
    if isinstance(value, list):
        return [_repair_payload(item, key=key) for item in value]
    if isinstance(value, tuple):
        return tuple(_repair_payload(item, key=key) for item in value)
    if isinstance(value, dict):
        return {item_key: _repair_payload(item, key=str(item_key)) for item_key, item in value.items()}
    return value


def _is_technical_token(value: str) -> bool:
    stripped = value.strip()
    return bool(stripped and TECHNICAL_TOKEN_RE.fullmatch(stripped))


def _is_url_or_doi(value: str) -> bool:
    return bool(URL_OR_DOI_RE.match(value.strip()))


def _repair_utf8_misdecoded(value: str) -> str:
    best = value
    for encoding in ("cp1251", "latin1"):
        try:
            candidate = value.encode(encoding).decode("utf-8")
        except UnicodeError:
            continue
        if _badness(candidate) < _badness(best):
            best = candidate
    return best


def _repair_mixed_cp1251_latin1(value: str) -> str:
    if _is_technical_token(value):
        return value
    bytes_out = bytearray()
    for char in value:
        code = ord(char)
        if code <= 0xFF:
            bytes_out.append(code)
            continue
        try:
            encoded = char.encode("cp1251")
        except UnicodeError:
            return value
        if len(encoded) != 1:
            return value
        bytes_out.extend(encoded)
    try:
        candidate = bytes(bytes_out).decode("utf-8")
    except UnicodeError:
        return value
    return candidate if _badness(candidate) < _badness(value) else value


def _repair_utf16_lowbyte(value: str) -> str:
    if _is_technical_token(value) or not _looks_like_utf16_lowbyte(value):
        return value
    chars: list[str] = []
    for index, char in enumerate(value):
        code = ord(char)
        previous_char = value[index - 1] if index else ""
        next_char = value[index + 1] if index + 1 < len(value) else ""
        if code == 0x13 and previous_char.isdigit() and next_char.isdigit():
            chars.append("-")
        elif char.isdigit() and _is_digit_in_numeric_run(value, index):
            chars.append(char)
        elif code == 0x01:
            chars.append("Ё")
        elif code == 0x51:
            chars.append("ё")
        elif char == ":" and (next_char in "* \n\r\t" or previous_char in "* \n\r\t"):
            chars.append(char)
        elif 0x10 <= code <= 0x2F and (code < 0x20 or ((not char.isspace()) and char not in ",.:-/()[]{}*_\"'`")):
            chars.append(chr(0x0400 + code))
        elif 0x30 <= code <= 0x4F:
            chars.append(chr(0x0400 + code))
        else:
            chars.append(char)
    candidate = "".join(chars)
    return candidate if _badness(candidate) < _badness(value) else value




def _is_digit_in_numeric_run(value: str, index: int) -> bool:
    start = index
    while start > 0 and value[start - 1].isdigit():
        start -= 1
    end = index
    while end + 1 < len(value) and value[end + 1].isdigit():
        end += 1
    if end == start:
        return False
    before = value[start - 1] if start > 0 else ""
    after = value[end + 1] if end + 1 < len(value) else ""
    safe_before = before == "" or before.isspace() or before in "([{-–—/~\x13"
    safe_after = after == "" or after.isspace() or after in ")]}.,;:%/~-–—\x13"
    return safe_before and safe_after

def _looks_like_utf16_lowbyte(value: str) -> bool:
    if not value or _is_technical_token(value):
        return False
    control_count = sum(1 for char in value if ord(char) < 0x20 and char not in "\n\r\t")
    cyrillic_count = sum(1 for char in value if "А" <= char <= "я" or char in "Ёё")
    lowbyte_like = sum(1 for char in value if char in "0123456789:;<=>?@ABCDEFGHIJKLMNOQ")
    if control_count >= 1:
        return True
    if cyrillic_count > 0:
        return False
    if "_" in value and re.fullmatch(r"[A-Za-z0-9_:/.-]+", value.strip()):
        return False
    return lowbyte_like >= max(8, len(value) // 4)


def _badness(value: str) -> int:
    cyrillic_count = sum(1 for char in value if "А" <= char <= "я" or char in "Ёё")
    marker_score = sum(value.count(marker) for marker in MOJIBAKE_MARKERS) * 10
    marker_score += len(re.findall(r"[РС][\u0400-\u04ff°-ї]", value)) * 8
    control_score = sum(1 for char in value if ord(char) < 0x20 and char not in "\n\r\t") * 8
    lowbyte_score = 0 if cyrillic_count else sum(1 for char in value if char in "0123456789:;<=>?@ABCDEFGHIJKLMNOQ")
    replacement_score = value.count("?") if any(marker in value for marker in MOJIBAKE_MARKERS) else 0
    return marker_score + control_score + lowbyte_score + replacement_score




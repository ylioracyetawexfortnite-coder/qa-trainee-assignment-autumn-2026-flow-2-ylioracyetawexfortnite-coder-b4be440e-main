"""Вспомогательные функции: генерация данных и разбор ответов."""

import re
import uuid
from typing import Any

UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")

DEFAULT_STATS = {"likes": 21, "viewCount": 11, "contacts": 43}


def unique_username(prefix: str = "qa") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def unique_password() -> str:
    return f"Pw-{uuid.uuid4().hex[:10]}!"


def unique_item_name() -> str:
    return f"item-{uuid.uuid4().hex[:10]}"


def build_item_payload(seller_id: Any, **overrides: Any) -> dict:
    """Корректное тело POST /api/1/item. Любое поле можно переопределить через overrides."""
    payload = {
        "sellerID": seller_id,
        "name": unique_item_name(),
        "price": 9900,
        "statistics": dict(DEFAULT_STATS),
    }
    payload.update(overrides)
    return payload


def json_body(resp) -> Any:
    """Тело ответа как JSON или None, если это не JSON."""
    try:
        return resp.json()
    except ValueError:
        return None


def extract_item_id(resp) -> str | None:
    """Достаёт UUID из ответа POST /api/1/item ({"status": "Сохранили объявление - <uuid>"})."""
    data = json_body(resp)
    text = data.get("status", "") if isinstance(data, dict) else ""
    if not text:
        text = resp.text or ""
    match = UUID_RE.search(str(text))
    return match.group(0) if match else None


def first(data: Any) -> Any:
    """Сервис может вернуть объект или список из одного объекта — приводим к объекту."""
    if isinstance(data, list):
        assert data, "ожидался непустой список"
        return data[0]
    return data


def as_list(data: Any) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list):
                return value
    return [] if data in (None, {}) else [data]


def pick(data: dict, *keys: str) -> Any:
    """Значение по первому найденному ключу (sellerID / sellerId, viewCount / viewcount)."""
    lowered = {k.lower(): v for k, v in data.items()}
    for key in keys:
        if key.lower() in lowered:
            return lowered[key.lower()]
    raise AssertionError(f"ни одного из ключей {keys} нет в ответе: {list(data)}")

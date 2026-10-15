"""Диагностика зависаний стенда. Запуск: python scripts/diag_hang.py

Проверяет по очереди, какие запросы реально вешают сервис и как долго он потом «приходит в себя».
Каждый шаг печатает код ответа и время. Результат сохраняется в docs/diag_hang_report.md.
Скрипт отправляет немного запросов (десятки), создаёт и сразу удаляет свои объявления.
"""

import os
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import BASE_URL  # noqa: E402
from src.helpers import (
    build_item_payload,
    extract_item_id,
    unique_password,
    unique_username,
)  # noqa: E402

TIMEOUT = float(os.getenv("DIAG_TIMEOUT", "20"))
REPORT = Path(__file__).resolve().parents[1] / "docs" / "diag_hang_report.md"
LINES: list[str] = []


def log(text: str) -> None:
    print(text, flush=True)
    LINES.append(text)


def call(method, path, token=None, **kw):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    started = time.monotonic()
    try:
        r = requests.request(method, BASE_URL + path, headers=headers, timeout=TIMEOUT, **kw)
        return r, time.monotonic() - started
    except requests.Timeout:
        return None, time.monotonic() - started


def describe(r, took):
    return f"HTTP {r.status_code} за {took:.2f} с" if r is not None else f"ТАЙМАУТ {took:.0f} с"


def create_and_delete(token, seller_id, **overrides):
    """Создаёт объявление и сразу удаляет его. Возвращает (ответ, время, id)."""
    r, took = call("POST", "/api/1/item", token, json=build_item_payload(seller_id, **overrides))
    item_id = extract_item_id(r) if r is not None and r.status_code in (200, 201) else None
    if item_id:
        call("DELETE", f"/api/2/item/{item_id}", token)
    return r, took, item_id


def wait_recovery(token, seller_id, limit=300):
    """Опрашивает POST /api/1/item раз в 5 с, пока не ответит. Возвращает секунды или None."""
    started = time.monotonic()
    while time.monotonic() - started < limit:
        r, took, _ = create_and_delete(token, seller_id)
        if r is not None and r.status_code in (200, 201):
            return time.monotonic() - started
        time.sleep(5)
    return None


def main():
    log(f"# Диагностика зависаний: {BASE_URL}\n")

    # 0. пользователь
    username, password = unique_username("diag"), unique_password()
    r, took = call("POST", "/api/1/register", json={"username": username, "password": password})
    log(f"0. регистрация: {describe(r, took)}")
    if r is None or r.status_code != 201:
        log("Регистрация не прошла, дальше идти нет смысла. Повторите позже.")
        return finish()
    seller_id = r.json()["id"]
    r, took = call("POST", "/api/1/autorize", json={"username": username, "password": password})
    log(f"0. авторизация: {describe(r, took)}")
    token = r.json()["accessToken"]

    # 1. базовая линия
    log("\n## 1. Базовая линия: создание объявления 5 раз подряд")
    for i in range(5):
        r, took, _ = create_and_delete(token, seller_id)
        log(f"- #{i + 1}: {describe(r, took)}")

    # 2. большие числа
    log("\n## 2. Большие значения статистики (2147483647) на живом стенде")
    big = {"likes": 2147483647, "viewCount": 2147483647, "contacts": 2147483647}
    r, took, _ = create_and_delete(token, seller_id, statistics=big)
    log(f"- POST /api/1/item: {describe(r, took)}")
    if r is None:
        log(f"- стенд ожил через {wait_recovery(token, seller_id)} с")

    # 3. подозреваемый запрос: длинный id в v1 и v2
    for version in ("1", "2"):
        log(f"\n## 3.{version}. GET /api/{version}/statistic/<300 символов 'a'>")
        r, took = call("GET", f"/api/{version}/statistic/{'a' * 300}", token)
        log(f"- сам запрос: {describe(r, took)}")
        r2, took2, _ = create_and_delete(token, seller_id)
        log(f"- сразу после него POST /api/1/item: {describe(r2, took2)}")
        if r2 is None or r2.status_code not in (200, 201):
            recovered = wait_recovery(token, seller_id)
            log(
                "- стенд так и не ожил за 300 с"
                if recovered is None
                else f"- POST /api/1/item снова отвечает через {recovered:.0f} с"
            )

    # 4. повтор подозреваемого запроса: воспроизводится ли
    log("\n## 4. Повтор GET /api/2/statistic/<300 'a'> ещё 3 раза (по 20 с пауза между)")
    for i in range(3):
        r, took = call("GET", f"/api/2/statistic/{'a' * 300}", token)
        log(f"- #{i + 1}: {describe(r, took)}")
        time.sleep(20)

    # 5. другие длины id
    log("\n## 5. Граница по длине id для v2")
    for n in (50, 100, 200, 250, 300, 500):
        r, took = call("GET", f"/api/2/statistic/{'a' * n}", token)
        log(f"- {n} символов: {describe(r, took)}")

    return finish()


def finish():
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
    print(f"\nОтчёт сохранён: {REPORT}")


if __name__ == "__main__":
    main()

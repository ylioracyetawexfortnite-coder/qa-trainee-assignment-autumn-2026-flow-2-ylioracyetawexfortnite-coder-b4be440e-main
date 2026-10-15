"""Тонкая обёртка над requests: один метод на ручку + вложения в Allure."""

import copy
import json
from typing import Any

import allure
import requests

from src.config import BASE_URL, REQUEST_TIMEOUT

_SECRET_KEYS = {"password", "accesstoken"}


def _mask(value: Any) -> Any:
    """Прячем пароли и токены в вложениях отчёта."""
    value = copy.deepcopy(value)
    if isinstance(value, dict):
        for key in list(value):
            if key.lower() in _SECRET_KEYS:
                value[key] = "***"
    return value


class ServiceTimeout(AssertionError):
    """Сервис не ответил за отведённое время (зависание запроса)."""


class ApiClient:
    def __init__(self, base_url: str = BASE_URL, timeout: float = REQUEST_TIMEOUT):
        self.base_url = base_url
        self.timeout = timeout
        self.session = requests.Session()
        # True после любого таймаута: conftest перед следующим тестом дождётся, пока стенд оживёт
        self.degraded = False

    def request(
        self,
        method: str,
        path: str,
        token: str | None = None,
        headers: dict | None = None,
        **kwargs: Any,
    ) -> requests.Response:
        """token=None -> запрос без Authorization. Нестандартный заголовок — через headers."""
        req_headers = {"Accept": "application/json"}
        if token:
            req_headers["Authorization"] = f"Bearer {token}"
        if headers:
            req_headers.update(headers)
        url = f"{self.base_url}{path}"
        timeout = kwargs.pop("timeout", self.timeout)

        with allure.step(f"{method} {path}"):
            shown_headers = {
                k: ("Bearer ***" if k.lower() == "authorization" else v)
                for k, v in req_headers.items()
            }
            allure.attach(
                json.dumps(shown_headers, ensure_ascii=False, indent=2),
                "request headers",
                allure.attachment_type.JSON,
            )
            if "json" in kwargs:
                allure.attach(
                    json.dumps(_mask(kwargs["json"]), ensure_ascii=False, indent=2),
                    "request body",
                    allure.attachment_type.JSON,
                )
            elif "data" in kwargs:
                allure.attach(
                    str(kwargs["data"]), "request body (raw)", allure.attachment_type.TEXT
                )

            try:
                resp = self.session.request(
                    method, url, headers=req_headers, timeout=timeout, **kwargs
                )
            except requests.Timeout as e:
                self.degraded = True
                short = path if len(path) <= 80 else path[:77] + "..."
                raise ServiceTimeout(
                    f"сервис не ответил за {timeout} с: {method} {short} (зависание)"
                ) from e

            try:
                shown = json.dumps(_mask(resp.json()), ensure_ascii=False, indent=2)
                kind = allure.attachment_type.JSON
            except ValueError:
                shown, kind = resp.text[:2000], allure.attachment_type.TEXT
            allure.attach(
                f"HTTP {resp.status_code} ({resp.elapsed.total_seconds():.3f}s)\n{shown}",
                "response",
                kind,
            )
        return resp

    # --- пользователи ---
    def register(self, username: Any, password: Any, **kw: Any):
        return self.request(
            "POST", "/api/1/register", json={"username": username, "password": password}, **kw
        )

    def authorize(self, username: Any, password: Any, **kw: Any):
        return self.request(
            "POST", "/api/1/autorize", json={"username": username, "password": password}, **kw
        )

    # --- объявления ---
    def create_item(self, payload: Any, token: str | None, **kw: Any):
        return self.request("POST", "/api/1/item", token=token, json=payload, **kw)

    def get_item(self, item_id: Any, token: str | None):
        return self.request("GET", f"/api/1/item/{item_id}", token=token)

    def get_seller_items(self, seller_id: Any, token: str | None):
        return self.request("GET", f"/api/1/{seller_id}/item", token=token)

    def delete_item(self, item_id: Any, token: str | None):
        return self.request("DELETE", f"/api/2/item/{item_id}", token=token)

    # --- статистика ---
    def stat_v1(self, item_id: Any, token: str | None):
        return self.request("GET", f"/api/1/statistic/{item_id}", token=token)

    def stat_v2(self, item_id: Any, token: str | None):
        return self.request("GET", f"/api/2/statistic/{item_id}", token=token)

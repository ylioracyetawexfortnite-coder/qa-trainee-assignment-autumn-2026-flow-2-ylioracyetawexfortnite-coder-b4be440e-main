"""Локальный мок-сервис по описанию из задания. Нужен, чтобы проверить сам тестовый проект
офлайн (без обращения к общему стенду).

Запуск:   python tools/mock_server.py [--port 8080]
Прогон:   BASE_URL=http://127.0.0.1:8080 pytest

Для проверки, что тесты ловят дефекты, можно включить «баги»:
    MOCK_BUGS=spoof,noauth_delete,double_delete_ok,neg_price python tools/mock_server.py

Режим «stall» имитирует зависание стенда: GET /api/2/statistic/<id длиннее 200 символов> и все
POST /api/1/item в течение MOCK_STALL_SECONDS (по умолчанию 40) после него не отвечают.
Нужен, чтобы проверить защиту тестов от каскада таймаутов (stand-guard в conftest.py).
"""

import argparse
import json
import os
import re
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

BUGS = {b for b in os.getenv("MOCK_BUGS", "").split(",") if b}
if "real" in BUGS:  # поведение реального стенда по результатам probe
    BUGS |= {"foreign_delete", "stats_after_delete", "neg_price", "neg_stats", "zero_missing"}
STATS: dict[str, dict] = {}  # статистика живёт отдельно от объявлений
LOCK = threading.Lock()
USERS: dict[str, dict] = {}  # username -> {id, password}
TOKENS: dict[str, int] = {}  # token -> user id
ITEMS: dict[str, dict] = {}  # uuid -> item
NEXT_ID = [1000]
STALL_SECONDS = float(os.getenv("MOCK_STALL_SECONDS", "40"))
STALL_UNTIL = [0.0]

MAX_INT64 = 2**63 - 1


def is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # тишина в консоли
        pass

    # ---------- утилиты ----------
    def send_json(self, code, payload=None):
        body = b"" if payload is None else json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def error(self, code, message):
        self.send_json(code, {"result": {"message": message, "messages": {}}, "status": str(code)})

    def read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            return json.loads(raw)
        except ValueError:
            return None

    def auth_user(self):
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return None
        return TOKENS.get(header[len("Bearer ") :])

    # ---------- маршрутизация ----------
    def route(self, method):
        path = unquote(self.path.split("?")[0])

        if "stall" in BUGS:
            if method == "GET" and path.startswith("/api/2/statistic/") and len(path) > 200:
                STALL_UNTIL[0] = time.monotonic() + STALL_SECONDS
            if method in ("GET", "POST") and (
                path.startswith("/api/2/statistic/")
                and len(path) > 200
                or (method == "POST" and path == "/api/1/item")
            ):
                remaining = STALL_UNTIL[0] - time.monotonic()
                if remaining > 0:
                    time.sleep(remaining)  # клиент к этому моменту уже отвалится по таймауту

        if method == "POST" and path == "/api/1/register":
            return self.register()
        if method == "POST" and path == "/api/1/autorize":
            return self.authorize()

        protected = [
            ("POST", r"^/api/1/item$", self.create_item),
            ("GET", r"^/api/1/item/([^/]+)$", self.get_item),
            ("GET", r"^/api/1/([^/]+)/item$", self.seller_items),
            ("GET", r"^/api/1/statistic/([^/]+)$", self.statistic),
            ("GET", r"^/api/2/statistic/([^/]+)$", self.statistic),
            ("DELETE", r"^/api/2/item/([^/]+)$", self.delete_item),
        ]
        for m, pattern, fn in protected:
            match = re.match(pattern, path)
            if m == method and match:
                uid = self.auth_user()
                if uid is None and not (fn == self.delete_item and "noauth_delete" in BUGS):
                    return self.error(401, "unauthorized")
                return fn(uid, *match.groups())
        return self.error(404, f"route {method}:{path} not found")

    def do_GET(self):
        self.route("GET")

    def do_POST(self):
        self.route("POST")

    def do_DELETE(self):
        self.route("DELETE")

    def do_PUT(self):
        self.route("PUT")

    def do_PATCH(self):
        self.route("PATCH")

    # ---------- пользователи ----------
    @staticmethod
    def valid_creds(body):
        return (
            isinstance(body, dict)
            and isinstance(body.get("username"), str)
            and isinstance(body.get("password"), str)
            and body["username"].strip() != ""
            and body["password"] != ""
        )

    def register(self):
        body = self.read_json()
        if not self.valid_creds(body):
            return self.error(400, "invalid username or password")
        with LOCK:
            if body["username"] in USERS:
                return self.error(409, "user already exists")
            NEXT_ID[0] += 1
            USERS[body["username"]] = {"id": NEXT_ID[0], "password": body["password"]}
            uid = NEXT_ID[0]
        self.send_json(201, {"id": uid, "username": body["username"]})

    def authorize(self):
        body = self.read_json()
        if not self.valid_creds(body):
            return self.error(400, "invalid username or password")
        user = USERS.get(body["username"])
        if not user or user["password"] != body["password"]:
            return self.error(401, "wrong credentials")
        token = f"mock.{uuid.uuid4().hex}.sig"
        TOKENS[token] = user["id"]
        self.send_json(200, {"accessToken": token, "tokenType": "Bearer"})

    # ---------- объявления ----------
    def create_item(self, uid):
        body = self.read_json()
        if not isinstance(body, dict):
            return self.error(400, "invalid body")
        seller, name, price, stats = (
            body.get(k) for k in ("sellerID", "name", "price", "statistics")
        )
        if not is_int(seller):
            return self.error(400, "sellerID must be integer")
        if seller != uid and "spoof" not in BUGS:
            return self.error(400, "sellerID must match authorized user")
        if not isinstance(name, str) or not name.strip():
            return self.error(400, "name is required")
        if not is_int(price) or price > MAX_INT64 or (price < 0 and "neg_price" not in BUGS):
            return self.error(400, "invalid price")
        if price == 0 and "zero_missing" in BUGS:
            return self.error(400, "поле price обязательно")
        if not isinstance(stats, dict):
            return self.error(400, "statistics is required")
        for key in ("likes", "viewCount", "contacts"):
            value = stats.get(key)
            if not is_int(value) or value > MAX_INT64:
                return self.error(400, f"invalid statistics.{key}")
            if value < 0 and "neg_stats" not in BUGS:
                return self.error(400, f"invalid statistics.{key}")
            if value == 0 and "zero_missing" in BUGS:
                return self.error(400, f"поле {key} обязательно")
        item_id = str(uuid.uuid4())
        with LOCK:
            ITEMS[item_id] = {
                "id": item_id,
                "sellerId": seller,
                "name": name,
                "price": price,
                "statistics": {k: stats[k] for k in ("likes", "viewCount", "contacts")},
                "createdAt": "2026-01-01 00:00:00 +0000 UTC",
            }
            STATS[item_id] = dict(ITEMS[item_id]["statistics"])
        self.send_json(200, {"status": f"Сохранили объявление - {item_id}"})

    @staticmethod
    def parse_uuid(raw):
        try:
            return str(uuid.UUID(raw))
        except ValueError:
            return None

    def get_item(self, uid, raw_id):
        item_id = self.parse_uuid(raw_id)
        if not item_id:
            return self.error(400, "invalid id")
        item = ITEMS.get(item_id)
        if not item:
            return self.error(404, "item not found")
        self.send_json(200, [item])

    def seller_items(self, uid, raw_seller):
        if not re.fullmatch(r"\d+", raw_seller):
            return self.error(400, "invalid sellerID")
        found = [i for i in list(ITEMS.values()) if i["sellerId"] == int(raw_seller)]
        self.send_json(200, found)

    def statistic(self, uid, raw_id):
        item_id = self.parse_uuid(raw_id)
        if not item_id:
            return self.error(400, "invalid id")
        source = (
            STATS
            if "stats_after_delete" in BUGS
            else {i: v["statistics"] for i, v in ITEMS.items()}
        )
        stats = source.get(item_id)
        if stats is None:
            return self.error(404, "statistic not found")
        self.send_json(200, [stats])

    def delete_item(self, uid, raw_id):
        item_id = self.parse_uuid(raw_id)
        if not item_id:
            return self.error(400, "invalid id")
        with LOCK:
            item = ITEMS.get(item_id)
            if not item:
                if "double_delete_ok" in BUGS:
                    return self.send_json(200, None)
                return self.error(404, "item not found")
            if uid is not None and item["sellerId"] != uid and "foreign_delete" not in BUGS:
                return self.error(403, "forbidden")
            del ITEMS[item_id]
        self.send_json(200, None)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    print(f"Mock service on http://127.0.0.1:{args.port} (bugs: {sorted(BUGS) or 'none'})")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()

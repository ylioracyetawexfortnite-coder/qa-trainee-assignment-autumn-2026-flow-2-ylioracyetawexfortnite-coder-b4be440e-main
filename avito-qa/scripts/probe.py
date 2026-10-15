"""Разведка стенда: шлёт набор запросов и сохраняет коды и тела ответов в probe_report.md.

Нужен, чтобы увидеть РЕАЛЬНОЕ поведение сервиса (коды ошибок, формат ответов) до разбора
упавших тестов. Токены и пароли в отчёт не попадают.

Запуск:  python scripts/probe.py
"""

import json
import os
import sys
import uuid

import requests

BASE = os.getenv("BASE_URL", "https://qa-internship.avito.com").rstrip("/")
OUT = "probe_report.md"
lines: list[str] = []
created: list[tuple[str, str]] = []


def call(title, method, path, token=None, headers=None, **kw):
    h = {"Accept": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    h.update(headers or {})
    try:
        r = requests.request(method, BASE + path, headers=h, timeout=15, **kw)
        body = r.text
        try:
            data = r.json()
            if isinstance(data, dict) and "accessToken" in data:
                data["accessToken"] = "***"
            body = json.dumps(data, ensure_ascii=False)
        except ValueError:
            pass
        status = r.status_code
        ctype = r.headers.get("Content-Type", "")
        ms = int(r.elapsed.total_seconds() * 1000)
    except requests.RequestException as e:
        status, body, ctype, ms = "ERR", repr(e), "", 0
    lines.append(
        f"### {title}\n`{method} {path}` -> **{status}** ({ms} ms, {ctype})\n"
        f"```\n{body[:600]}\n```\n"
    )
    print(f"{status}  {method} {path}  [{title}]")
    return r if status != "ERR" else None


def item_id_from(resp):
    import re

    m = re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", resp.text or "")
    return m.group(0) if m else None


def main():
    tag = uuid.uuid4().hex[:10]
    u1, u2, pw = f"probe_a_{tag}", f"probe_b_{tag}", f"Pw-{tag}!"

    r = call("register A", "POST", "/api/1/register", json={"username": u1, "password": pw})
    call("register A duplicate", "POST", "/api/1/register", json={"username": u1, "password": pw})
    rb = call("register B", "POST", "/api/1/register", json={"username": u2, "password": pw})
    call("register empty body", "POST", "/api/1/register", json={})
    call(
        "register empty password",
        "POST",
        "/api/1/register",
        json={"username": f"x{tag}", "password": ""},
    )
    if not r or r.status_code not in (200, 201):
        print("Регистрация не удалась — дальше идти нет смысла")
        return finish()
    a_id, b_id = r.json()["id"], rb.json()["id"]

    ta = call(
        "authorize A", "POST", "/api/1/autorize", json={"username": u1, "password": pw}
    ).json()["accessToken"]
    tb = call(
        "authorize B", "POST", "/api/1/autorize", json={"username": u2, "password": pw}
    ).json()["accessToken"]
    call(
        "authorize wrong password",
        "POST",
        "/api/1/autorize",
        json={"username": u1, "password": "nope"},
    )
    call(
        "authorize unknown user",
        "POST",
        "/api/1/autorize",
        json={"username": f"no_{tag}", "password": pw},
    )

    def payload(seller, **over):
        p = {
            "sellerID": seller,
            "name": f"probe-{tag}",
            "price": 9900,
            "statistics": {"likes": 21, "viewCount": 11, "contacts": 43},
        }
        p.update(over)
        return p

    def create(title, token, body, owner_token=None):
        resp = call(title, "POST", "/api/1/item", token=token, json=body)
        iid = item_id_from(resp) if resp is not None and resp.status_code in (200, 201) else None
        if iid:
            created.append((iid, owner_token or token))
        return iid

    iid = create("create item", ta, payload(a_id))
    create("create item without token", None, payload(a_id))
    create("create item foreign sellerID", ta, payload(b_id), owner_token=ta)
    call(
        "create item X-UserId header",
        "POST",
        "/api/1/item",
        token=ta,
        headers={"X-UserId": str(b_id)},
        json=payload(b_id),
    )
    create("create negative price", ta, payload(a_id, price=-1))
    create("create zero price", ta, payload(a_id, price=0))
    create("create empty name", ta, payload(a_id, name=""))
    create("create price as string", ta, payload(a_id, price="100"))
    create("create price float", ta, payload(a_id, price=99.99))
    create(
        "create negative likes",
        ta,
        payload(a_id, statistics={"likes": -1, "viewCount": 1, "contacts": 1}),
    )
    create(
        "create no statistics", ta, {k: v for k, v in payload(a_id).items() if k != "statistics"}
    )
    create("create name 1000 chars", ta, payload(a_id, name="n" * 1000))

    if iid:
        call("get item", "GET", f"/api/1/item/{iid}", token=ta)
        call("get item without token", "GET", f"/api/1/item/{iid}")
        call("get item by other user", "GET", f"/api/1/item/{iid}", token=tb)
        call("seller items", "GET", f"/api/1/{a_id}/item", token=ta)
        call("statistic v1", "GET", f"/api/1/statistic/{iid}", token=ta)
        call("statistic v2", "GET", f"/api/2/statistic/{iid}", token=ta)
        call("delete item v1 path", "DELETE", f"/api/1/item/{iid}", token=ta)
        call("delete foreign item", "DELETE", f"/api/2/item/{iid}", token=tb)
    call("get unknown item", "GET", f"/api/1/item/{uuid.uuid4()}", token=ta)
    call("get invalid id", "GET", "/api/1/item/abc", token=ta)
    call("seller items of B (empty)", "GET", f"/api/1/{b_id}/item", token=tb)
    call("seller items invalid id", "GET", "/api/1/abc/item", token=ta)
    call("statistic unknown id v1", "GET", f"/api/1/statistic/{uuid.uuid4()}", token=ta)
    call("statistic unknown id v2", "GET", f"/api/2/statistic/{uuid.uuid4()}", token=ta)
    call("bad token", "GET", f"/api/1/{a_id}/item", token="garbage")

    if iid:
        call("delete item v2", "DELETE", f"/api/2/item/{iid}", token=ta)
        call("delete item again", "DELETE", f"/api/2/item/{iid}", token=ta)
        call("get deleted item", "GET", f"/api/1/item/{iid}", token=ta)
        call("statistic deleted v1", "GET", f"/api/1/statistic/{iid}", token=ta)
        call("statistic deleted v2", "GET", f"/api/2/statistic/{iid}", token=ta)
    finish()


def finish():
    for item, token in created:  # уборка
        try:
            requests.delete(
                f"{BASE}/api/2/item/{item}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
            )
        except requests.RequestException:
            pass
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(f"# Probe report for {BASE}\n\n" + "\n".join(lines))
    print(f"\nГотово: {OUT}")


if __name__ == "__main__":
    sys.exit(main())

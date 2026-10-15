"""Проверка доступа к защищённым ручкам и подмены пользователя."""

import uuid

import allure
import pytest

from src.helpers import as_list, build_item_payload, extract_item_id, pick
from tests.conftest import OK_CREATE, assert_client_error

pytestmark = [allure.feature("Безопасность и доступ"), pytest.mark.security]

FAKE_ID = "11111111-1111-4111-8111-111111111111"

PROTECTED = [
    ("POST", "/api/1/item"),
    ("GET", "/api/1/item/{id}"),
    ("GET", "/api/1/{seller}/item"),
    ("GET", "/api/1/statistic/{id}"),
    ("GET", "/api/2/statistic/{id}"),
    ("DELETE", "/api/2/item/{id}"),
]


def call(api, method, template, item_id, seller_id, token, headers=None):
    path = template.format(id=item_id, seller=seller_id)
    kwargs = {"json": build_item_payload(seller_id)} if method == "POST" else {}
    return api.request(method, path, token=token, headers=headers, **kwargs)


@allure.title("TC-SEC-01 {method} {template} без токена -> 401")
@pytest.mark.parametrize("method, template", PROTECTED)
def test_protected_without_token(api, user, item, method, template):
    resp = call(api, method, template, item.id, user.id, token=None)
    assert resp.status_code == 401, f"ожидали 401, получили {resp.status_code}: {resp.text[:200]}"


@allure.title("TC-SEC-02 {method} {template} с невалидным токеном -> 401")
@pytest.mark.parametrize("method, template", PROTECTED)
def test_protected_with_garbage_token(api, user, item, method, template):
    resp = call(api, method, template, item.id, user.id, token="garbage.token.value")
    assert resp.status_code == 401


@allure.title("TC-SEC-03 Некорректный заголовок Authorization: {case}")
@pytest.mark.parametrize(
    "case, header",
    [
        ("пустое значение", ""),
        ("только схема", "Bearer"),
        ("схема и пробел", "Bearer "),
        ("Basic вместо Bearer", "Basic dXNlcjpwYXNz"),
        ("мусор", "abc"),
        ("JWT-подобный мусор", "Bearer aaa.bbb.ccc"),
    ],
)
def test_malformed_authorization_header(api, user, case, header):
    resp = api.request("GET", f"/api/1/{user.id}/item", headers={"Authorization": header})
    assert resp.status_code == 401


@allure.title("TC-SEC-04 Токен без префикса Bearer не принимается")
def test_token_without_bearer_prefix(api, user):
    resp = api.request("GET", f"/api/1/{user.id}/item", headers={"Authorization": user.token})
    assert resp.status_code == 401


@allure.title("TC-SEC-05 Токен с изменённой подписью не принимается")
def test_tampered_token(api, user):
    last = user.token[-1]
    tampered = user.token[:-1] + ("A" if last != "A" else "B")
    resp = api.get_seller_items(user.id, tampered)
    assert resp.status_code == 401


@allure.title("TC-SEC-06 Нельзя создать объявление с чужим sellerID")
def test_cannot_create_item_for_another_seller(api, user, other_user, item_factory):
    payload = build_item_payload(other_user.id)  # токен user, sellerID другого
    resp = item_factory.create_raw(user, payload)
    assert_client_error(resp)
    victim_items = as_list(api.get_seller_items(other_user.id, other_user.token).json())
    assert victim_items == [], "у жертвы появилось чужое объявление"


@allure.title("TC-SEC-07 Заголовок X-UserId не подменяет пользователя из токена")
def test_x_userid_header_ignored(api, user, other_user, item_factory):
    payload = build_item_payload(other_user.id)
    resp = api.create_item(payload, user.token, headers={"X-UserId": str(other_user.id)})
    if resp.status_code in OK_CREATE:  # если создалось — это дефект, чистим за собой
        item_factory._created.append((extract_item_id(resp), user))
    assert_client_error(resp)


@allure.title("TC-SEC-08 X-UserId не меняет владельца при корректном sellerID")
def test_x_userid_does_not_change_owner(api, user, other_user, item_factory):
    payload = build_item_payload(user.id)
    resp = api.create_item(payload, user.token, headers={"X-UserId": str(other_user.id)})
    if resp.status_code in OK_CREATE:
        item_factory._created.append((extract_item_id(resp), user))
        data = api.get_item(extract_item_id(resp), user.token).json()
        data = data[0] if isinstance(data, list) else data
        assert pick(data, "sellerID", "sellerId") == user.id
    else:
        assert_client_error(resp)


@allure.title("TC-SEC-09 Пользователь не может удалить чужое объявление")
@pytest.mark.xfail(reason="BUG-1: любой пользователь может удалить чужое объявление", strict=True)
def test_cannot_delete_foreign_item(api, user, other_user, item):
    resp = api.delete_item(item.id, other_user.token)
    assert_client_error(resp)
    assert api.get_item(item.id, user.token).status_code == 200, "чужое объявление удалено"


@allure.title("TC-SEC-10 Ошибки не раскрывают внутренние детали (stack trace, SQL)")
@pytest.mark.parametrize(
    "path", ["/api/1/item/'", "/api/1/item/abc", "/api/2/statistic/%00", "/api/1/abc/item"]
)
def test_errors_do_not_leak_internals(api, user, path):
    resp = api.request("GET", path, token=user.token)
    text = resp.text.lower()
    for marker in ("traceback", "stack trace", "sqlstate", "syntax error", "at java.", "panic:"):
        assert marker not in text, f"в ответе утечка: {marker!r}"


@allure.title("TC-SEC-11 Неизвестный маршрут возвращает 4xx")
def test_unknown_route(api, user):
    assert_client_error(api.request("GET", f"/api/1/unknown/{uuid.uuid4()}", token=user.token))

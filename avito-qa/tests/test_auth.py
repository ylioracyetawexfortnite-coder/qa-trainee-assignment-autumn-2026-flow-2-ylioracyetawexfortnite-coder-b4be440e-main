"""Регистрация и авторизация."""

import allure
import pytest
from jsonschema import validate

from src.helpers import json_body, unique_password, unique_username
from src.schemas import AUTHORIZE_RESPONSE, REGISTER_RESPONSE
from tests.conftest import assert_accepted_or_rejected, assert_client_error

pytestmark = allure.feature("Регистрация и авторизация")


@allure.title("TC-AUTH-01 Регистрация нового пользователя")
@pytest.mark.smoke
def test_register_success(api):
    username, password = unique_username(), unique_password()
    resp = api.register(username, password)
    assert resp.status_code == 201
    body = resp.json()
    validate(body, REGISTER_RESPONSE)
    assert body["username"] == username
    assert "password" not in {k.lower() for k in body}, "пароль не должен возвращаться"


@allure.title("TC-AUTH-02 У разных пользователей разные id")
def test_register_unique_ids(user, other_user):
    assert user.id != other_user.id


@allure.title("TC-AUTH-03 Повторная регистрация того же username отклоняется")
@pytest.mark.negative
def test_register_duplicate_username(api, user):
    resp = api.register(user.username, unique_password())
    assert_client_error(resp)
    # исходный пользователь не пострадал: старый пароль по-прежнему работает
    assert api.authorize(user.username, user.password).status_code == 200


@allure.title("TC-AUTH-04 Регистрация с некорректным телом: {case}")
@pytest.mark.negative
@pytest.mark.parametrize(
    "case, body",
    [
        pytest.param(
            "пустой объект",
            {},
            marks=pytest.mark.xfail(reason="BUG-5: POST /register с {} зависает", strict=False),
        ),
        ("нет username", {"password": "Pw-123456!"}),
        ("нет password", {"username": "no_pass_user"}),
        ("username пустой", {"username": "", "password": "Pw-123456!"}),
        ("password пустой", {"username": "empty_pass_user", "password": ""}),
        ("username null", {"username": None, "password": "Pw-123456!"}),
        ("password null", {"username": "null_pass_user", "password": None}),
        ("username число", {"username": 12345, "password": "Pw-123456!"}),
        ("password число", {"username": "int_pass_user", "password": 123456}),
        ("username массив", {"username": ["a"], "password": "Pw-123456!"}),
    ],
)
def test_register_invalid_body(api, case, body):
    resp = api.request("POST", "/api/1/register", json=body)
    assert_client_error(resp)


@allure.title("TC-AUTH-05 Регистрация: невалидный JSON / пустое тело")
@pytest.mark.negative
@pytest.mark.parametrize(
    "raw", ["{not json", "", "[]", "null"], ids=["битый", "пустое", "массив", "null"]
)
def test_register_malformed_json(api, raw):
    resp = api.request(
        "POST", "/api/1/register", data=raw, headers={"Content-Type": "application/json"}
    )
    assert_client_error(resp)


@allure.title("TC-AUTH-06 Граничные значения username: {case}")
@pytest.mark.boundary
@pytest.mark.parametrize(
    "case, make",
    [
        ("1 символ", lambda: "a"),
        ("64 символа", lambda: unique_username() + "x" * 49),
        ("255 символов", lambda: unique_username() + "x" * 240),
        ("256 символов", lambda: unique_username() + "x" * 241),
        ("1000 символов", lambda: unique_username() + "x" * 985),
        ("кириллица", lambda: "пользователь_" + unique_username()),
        ("эмодзи", lambda: "user😀_" + unique_username()),
        ("пробелы внутри", lambda: "user name " + unique_username()),
        ("только пробелы", lambda: "   "),
        ("спецсимволы", lambda: "u!@#$%^&*()_" + unique_username()),
    ],
)
def test_register_username_boundaries(api, case, make):
    username, password = make(), unique_password()
    resp = api.register(username, password)
    assert_accepted_or_rejected(resp)
    if resp.status_code in (200, 201):  # принят -> должен уметь авторизоваться
        assert api.authorize(username, password).status_code == 200


@allure.title("TC-AUTH-07 Граничные значения password: {case}")
@pytest.mark.boundary
@pytest.mark.parametrize(
    "case, password",
    [
        ("1 символ", "a"),
        ("8 символов", "Abcd123!"),
        ("72 символа", "A1!" + "x" * 69),
        ("73 символа", "A1!" + "x" * 70),
        ("256 символов", "A1!" + "x" * 253),
        ("1000 символов", "A1!" + "x" * 997),
        ("кириллица", "Пароль-123!"),
        ("только пробелы", "        "),
    ],
)
def test_register_password_boundaries(api, case, password):
    username = unique_username()
    resp = api.register(username, password)
    assert_accepted_or_rejected(resp)
    if resp.status_code in (200, 201):
        assert api.authorize(username, password).status_code == 200


@allure.title("TC-AUTH-08 Инъекции в username не ломают сервис: {payload}")
@pytest.mark.security
@pytest.mark.parametrize(
    "payload",
    ["' OR '1'='1", "admin'--", "<script>alert(1)</script>", '"; DROP TABLE users;--', "${7*7}"],
)
def test_register_injection_username(api, payload):
    username = f"{payload}{unique_username()}"
    resp = api.register(username, unique_password())
    assert_accepted_or_rejected(resp)


@allure.title("TC-AUTH-09 Успешная авторизация возвращает accessToken и tokenType")
@pytest.mark.smoke
def test_authorize_success(api, user):
    resp = api.authorize(user.username, user.password)
    assert resp.status_code == 200
    body = resp.json()
    validate(body, AUTHORIZE_RESPONSE)
    assert body["tokenType"] == "Bearer"
    assert "password" not in {k.lower() for k in body}


@allure.title("TC-AUTH-10 Неверный пароль")
@pytest.mark.negative
def test_authorize_wrong_password(api, user):
    resp = api.authorize(user.username, user.password + "x")
    assert_client_error(resp)
    assert "accessToken" not in (json_body(resp) or {})


@allure.title("TC-AUTH-11 Несуществующий пользователь")
@pytest.mark.negative
def test_authorize_unknown_user(api):
    resp = api.authorize(unique_username("ghost"), unique_password())
    assert_client_error(resp)
    assert "accessToken" not in (json_body(resp) or {})


@allure.title("TC-AUTH-12 Авторизация с некорректным телом: {case}")
@pytest.mark.negative
@pytest.mark.parametrize(
    "case, body",
    [
        ("пустой объект", {}),
        ("нет username", {"password": "Pw-123456!"}),
        ("нет password", {"username": "someone"}),
        ("пустые значения", {"username": "", "password": ""}),
        ("null", {"username": None, "password": None}),
    ],
)
def test_authorize_invalid_body(api, case, body):
    resp = api.request("POST", "/api/1/autorize", json=body)
    assert_client_error(resp)
    assert "accessToken" not in (json_body(resp) or {})


@allure.title("TC-AUTH-13 Пароль чувствителен к регистру")
@pytest.mark.negative
def test_authorize_password_case_sensitive(api, user):
    swapped = user.password.swapcase()
    assert swapped != user.password
    assert_client_error(api.authorize(user.username, swapped))


@allure.title("TC-AUTH-14 Токен открывает доступ к защищённой ручке")
@pytest.mark.smoke
def test_token_grants_access(api, user):
    resp = api.get_seller_items(user.id, user.token)
    assert resp.status_code == 200


@allure.title("TC-AUTH-15 Повторные логины выдают рабочие токены")
def test_multiple_logins_valid(api, user):
    second = api.authorize(user.username, user.password).json()["accessToken"]
    assert api.get_seller_items(user.id, user.token).status_code == 200
    assert api.get_seller_items(user.id, second).status_code == 200


@allure.title("TC-AUTH-16 Публичные ручки не требуют токена")
def test_public_endpoints_without_token(api):
    username, password = unique_username(), unique_password()
    assert api.register(username, password).status_code == 201  # без Authorization
    assert api.authorize(username, password).status_code == 200


@allure.title("TC-AUTH-17 Неподдерживаемые методы на /register и /autorize")
@pytest.mark.negative
@pytest.mark.parametrize("path", ["/api/1/register", "/api/1/autorize"])
@pytest.mark.parametrize("method", ["GET", "PUT", "DELETE"])
def test_auth_endpoints_wrong_method(api, method, path):
    assert_client_error(api.request(method, path))

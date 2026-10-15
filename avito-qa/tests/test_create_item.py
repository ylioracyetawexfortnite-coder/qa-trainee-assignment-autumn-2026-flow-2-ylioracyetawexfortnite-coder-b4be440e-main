"""POST /api/1/item."""

import uuid
from concurrent.futures import ThreadPoolExecutor

import allure
import pytest

from src.config import MAX_RESPONSE_TIME
from src.helpers import UUID_RE, build_item_payload, extract_item_id, json_body, pick
from tests.conftest import (
    OK_CREATE,
    assert_accepted_or_rejected,
    assert_client_error,
    read_item,
)

pytestmark = allure.feature("Создание объявления")


@allure.title("TC-ITEM-01 Создание объявления: ответ содержит UUID")
@pytest.mark.smoke
def test_create_item_success(api, user, item_factory):
    payload = build_item_payload(user.id)
    resp = item_factory.create_raw(user, payload)
    assert resp.status_code in OK_CREATE
    assert "application/json" in resp.headers.get("Content-Type", "")
    status_text = json_body(resp)["status"]
    assert UUID_RE.fullmatch(extract_item_id(resp)), status_text
    uuid.UUID(extract_item_id(resp))  # валидный UUID


@allure.title("TC-ITEM-02 Созданное объявление читается и совпадает с отправленным")
@pytest.mark.smoke
def test_created_item_matches_payload(api, user, item):
    data = read_item(api, item.id, user.token)
    assert pick(data, "id") == item.id
    assert pick(data, "name") == item.payload["name"]
    assert pick(data, "price") == item.payload["price"]
    assert pick(data, "sellerID", "sellerId") == user.id
    stats = pick(data, "statistics")
    for key, value in item.payload["statistics"].items():
        assert pick(stats, key) == value


@allure.title("TC-ITEM-03 Одинаковые данные допустимы, UUID у объявлений разные")
def test_duplicate_payloads_get_unique_ids(api, user, item_factory):
    same = {
        "name": "same-name",
        "price": 100,
        "statistics": {"likes": 1, "viewCount": 1, "contacts": 1},
    }
    a = item_factory.create(user, **same)
    b = item_factory.create(user, **same)
    assert a.id != b.id
    assert read_item(api, a.id, user.token) and read_item(api, b.id, user.token)


@allure.title("TC-ITEM-04 Нет обязательного поля: {field}")
@pytest.mark.negative
@pytest.mark.parametrize("field", ["sellerID", "name", "price"])
def test_missing_required_field(user, item_factory, field):
    payload = build_item_payload(user.id)
    payload.pop(field)
    assert_client_error(item_factory.create_raw(user, payload))


@allure.title("TC-ITEM-05 Отсутствует блок statistics")
@pytest.mark.boundary
def test_missing_statistics(user, item_factory):
    payload = build_item_payload(user.id)
    payload.pop("statistics")
    assert_accepted_or_rejected(item_factory.create_raw(user, payload))


@allure.title("TC-ITEM-06 Неверный тип поля {field}={value!r}")
@pytest.mark.negative
@pytest.mark.parametrize(
    "field, value",
    [
        ("name", 123),
        ("name", None),
        ("name", ["a"]),
        ("name", {"a": 1}),
        ("price", "abc"),
        ("price", None),
        ("price", []),
        ("price", {}),
        ("sellerID", "abc"),
        ("sellerID", None),
        ("sellerID", []),
        ("statistics", "text"),
        ("statistics", None),
        ("statistics", []),
    ],
)
def test_wrong_field_type(user, item_factory, field, value):
    payload = build_item_payload(user.id, **{field: value})
    assert_client_error(item_factory.create_raw(user, payload))


@allure.title("TC-ITEM-07 Граничные значения price: {price}")
@pytest.mark.boundary
@pytest.mark.parametrize(
    "price",
    [0, 1, 2147483647, 2147483648, 9223372036854775807, 9223372036854775808, 99.99, "100", 1e20],
    ids=lambda v: repr(v),
)
def test_price_boundaries(api, user, item_factory, price):
    resp = item_factory.create_raw(user, build_item_payload(user.id, price=price))
    assert_accepted_or_rejected(resp)
    if resp.status_code in OK_CREATE:  # принято -> значение не должно искажаться
        stored = pick(read_item(api, extract_item_id(resp), user.token), "price")
        if isinstance(price, int):
            assert stored == price, f"цена искажена: отправили {price!r}, получили {stored!r}"
        else:  # сервис мог привести тип (например "100" -> 100), но не должен менять значение
            assert float(stored) == float(price), f"цена искажена: {price!r} -> {stored!r}"


@allure.title("TC-ITEM-08 Отрицательная цена отклоняется")
@pytest.mark.negative
@pytest.mark.boundary
@pytest.mark.parametrize(
    "price",
    [
        pytest.param(
            -1, marks=pytest.mark.xfail(reason="BUG-3: принимается отрицательная цена", strict=True)
        ),
        pytest.param(
            -100,
            marks=pytest.mark.xfail(reason="BUG-3: принимается отрицательная цена", strict=False),
        ),
        pytest.param(
            -2147483648,
            marks=pytest.mark.xfail(reason="BUG-3: принимается отрицательная цена", strict=False),
        ),
    ],
)
def test_negative_price_rejected(user, item_factory, price):
    assert_client_error(item_factory.create_raw(user, build_item_payload(user.id, price=price)))


@allure.title("TC-ITEM-09 Пустое название отклоняется")
@pytest.mark.negative
@pytest.mark.boundary
def test_empty_name_rejected(user, item_factory):
    assert_client_error(item_factory.create_raw(user, build_item_payload(user.id, name="")))


@allure.title("TC-ITEM-10 Граничные значения name: {case}")
@pytest.mark.boundary
@pytest.mark.parametrize(
    "case, name",
    [
        ("1 символ", "a"),
        ("только пробелы", "   "),
        ("255 символов", "n" * 255),
        ("256 символов", "n" * 256),
        ("1000 символов", "n" * 1000),
        ("10000 символов", "n" * 10000),
        ("кириллица", "Велосипед «Стелс» №1"),
        ("эмодзи", "Самокат 🛴🔥"),
        ("HTML/XSS", "<script>alert(1)</script>"),
        ("SQL-инъекция", "'; DROP TABLE items;--"),
        ("перенос строки", "line1\nline2\ttab"),
        ("кавычки и слеши", 'name "q" \\ / \''),
    ],
)
def test_name_boundaries(api, user, item_factory, case, name):
    resp = item_factory.create_raw(user, build_item_payload(user.id, name=name))
    assert_accepted_or_rejected(resp)
    if resp.status_code in OK_CREATE:
        stored = pick(read_item(api, extract_item_id(resp), user.token), "name")
        assert stored == name, "название сохранено не так, как отправлено"


@allure.title("TC-ITEM-11 Статистика: отрицательное значение {key}")
@pytest.mark.negative
@pytest.mark.parametrize(
    "key",
    [
        pytest.param(
            "likes",
            marks=pytest.mark.xfail(
                reason="BUG-4: принимается отрицательная статистика", strict=True
            ),
        ),
        pytest.param(
            "viewCount",
            marks=pytest.mark.xfail(
                reason="BUG-4: принимается отрицательная статистика", strict=False
            ),
        ),
        pytest.param(
            "contacts",
            marks=pytest.mark.xfail(
                reason="BUG-4: принимается отрицательная статистика", strict=False
            ),
        ),
    ],
)
def test_negative_statistics_rejected(user, item_factory, key):
    stats = {"likes": 1, "viewCount": 1, "contacts": 1, key: -1}
    assert_client_error(
        item_factory.create_raw(user, build_item_payload(user.id, statistics=stats))
    )


@allure.title("TC-ITEM-12 Статистика: неверный тип {key}")
@pytest.mark.negative
@pytest.mark.parametrize("key", ["likes", "viewCount", "contacts"])
@pytest.mark.parametrize("value", ["abc", None, [1]], ids=["строка", "null", "массив"])
def test_wrong_type_statistics(user, item_factory, key, value):
    stats = {"likes": 1, "viewCount": 1, "contacts": 1, key: value}
    assert_client_error(
        item_factory.create_raw(user, build_item_payload(user.id, statistics=stats))
    )


@allure.title("TC-ITEM-13 Статистика: нули и максимальные значения")
@pytest.mark.boundary
@pytest.mark.parametrize("value", [0, 2147483647], ids=["нули", "int32-max"])
def test_statistics_boundaries(api, user, item_factory, value):
    stats = {"likes": value, "viewCount": value, "contacts": value}
    resp = item_factory.create_raw(user, build_item_payload(user.id, statistics=stats))
    assert_accepted_or_rejected(resp)
    if resp.status_code in OK_CREATE:
        stored = pick(read_item(api, extract_item_id(resp), user.token), "statistics")
        assert all(pick(stored, k) == value for k in stats)


@allure.title("TC-ITEM-14 Статистика: часть полей отсутствует ({missing})")
@pytest.mark.boundary
@pytest.mark.parametrize("missing", ["likes", "viewCount", "contacts"])
def test_partial_statistics(user, item_factory, missing):
    stats = {"likes": 1, "viewCount": 1, "contacts": 1}
    stats.pop(missing)
    resp = item_factory.create_raw(user, build_item_payload(user.id, statistics=stats))
    assert_accepted_or_rejected(resp)


@allure.title("TC-ITEM-15 Некорректное тело запроса: {case}")
@pytest.mark.negative
@pytest.mark.parametrize(
    "case, raw",
    [("битый JSON", "{oops"), ("пустое тело", ""), ("массив", "[]"), ("строка", '"text"')],
)
def test_create_malformed_body(api, user, case, raw):
    resp = api.request(
        "POST",
        "/api/1/item",
        token=user.token,
        data=raw,
        headers={"Content-Type": "application/json"},
    )
    assert_client_error(resp)


@allure.title("TC-ITEM-16 Клиент не может задать id объявления сам")
@pytest.mark.security
def test_client_cannot_set_item_id(api, user, item_factory):
    forced = "00000000-0000-4000-8000-000000000001"
    payload = build_item_payload(user.id, id=forced)
    resp = item_factory.create_raw(user, payload)
    assert_accepted_or_rejected(resp)
    if resp.status_code in OK_CREATE:
        assert extract_item_id(resp) != forced


@allure.title("TC-ITEM-17 Лишние поля в теле не приводят к ошибке сервера")
@pytest.mark.boundary
def test_extra_fields_ignored(user, item_factory):
    payload = build_item_payload(user.id, extra="x", createdAt="2000-01-01", isAdmin=True)
    assert_accepted_or_rejected(item_factory.create_raw(user, payload))


@allure.title("TC-ITEM-18 Параллельное создание: все UUID уникальны")
@pytest.mark.nonfunctional
def test_concurrent_creation(user, item_factory):
    def create_one(_):
        return item_factory.create_raw(user, build_item_payload(user.id))

    with ThreadPoolExecutor(max_workers=5) as pool:
        responses = list(pool.map(create_one, range(5)))
    assert all(r.status_code in OK_CREATE for r in responses), [r.status_code for r in responses]
    ids = [extract_item_id(r) for r in responses]
    assert len(set(ids)) == 5, f"UUID повторяются: {ids}"


@allure.title("TC-ITEM-19 Время ответа на создание не превышает порог")
@pytest.mark.nonfunctional
def test_create_response_time(user, item_factory):
    resp = item_factory.create_raw(user, build_item_payload(user.id))
    assert resp.elapsed.total_seconds() < MAX_RESPONSE_TIME


@allure.title("TC-ITEM-20 Неподдерживаемые методы на /api/1/item: {method}")
@pytest.mark.negative
@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
def test_item_collection_wrong_method(api, user, method):
    assert_client_error(api.request(method, "/api/1/item", token=user.token))

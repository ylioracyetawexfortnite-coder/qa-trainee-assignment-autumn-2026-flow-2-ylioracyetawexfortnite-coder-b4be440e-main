"""GET /api/1/item/{id} и GET /api/1/{sellerID}/item."""

import uuid

import allure
import pytest

from src.helpers import as_list, json_body, pick
from tests.conftest import assert_accepted_or_rejected, assert_client_error, read_item

pytestmark = allure.feature("Получение объявлений")

BAD_IDS = [
    "abc",
    "123",
    "0",
    "-1",
    "%20",
    "0" * 36,
    "g" * 8 + "-gggg-gggg-gggg-" + "g" * 12,
    pytest.param("a" * 500, id="500 символов"),
    "' OR '1'='1",
    "..%2F..%2Fetc%2Fpasswd",
    "<script>alert(1)</script>",
]


@allure.title("TC-GET-01 Получение объявления по id")
@pytest.mark.smoke
def test_get_item_by_id(api, user, item):
    resp = api.get_item(item.id, user.token)
    assert resp.status_code == 200
    assert "application/json" in resp.headers.get("Content-Type", "")
    data = read_item(api, item.id, user.token)
    assert pick(data, "id") == item.id
    assert pick(data, "name") == item.payload["name"]
    assert pick(data, "sellerID", "sellerId") == user.id


@allure.title("TC-GET-02 Несуществующий id (валидный UUID) -> 404")
@pytest.mark.negative
def test_get_item_not_found(api, user):
    resp = api.get_item(uuid.uuid4(), user.token)
    assert_client_error(resp, allowed=(404,))


@allure.title("TC-GET-03 Некорректный формат id: {bad_id}")
@pytest.mark.negative
@pytest.mark.parametrize("bad_id", BAD_IDS)
def test_get_item_invalid_id(api, user, bad_id):
    assert_client_error(api.get_item(bad_id, user.token))


@allure.title("TC-GET-04 Объявление читается повторно без изменений (идемпотентность)")
def test_get_item_idempotent(api, user, item):
    first_read = api.get_item(item.id, user.token).json()
    second_read = api.get_item(item.id, user.token).json()
    assert first_read == second_read


@allure.title("TC-GET-05 Объявления продавца: содержит созданные и только свои")
@pytest.mark.smoke
def test_seller_items_contains_created(api, user, item_factory):
    a = item_factory.create(user)
    b = item_factory.create(user)
    resp = api.get_seller_items(user.id, user.token)
    assert resp.status_code == 200
    items = as_list(resp.json())
    ids = {pick(i, "id") for i in items}
    assert {a.id, b.id} <= ids
    assert all(pick(i, "sellerID", "sellerId") == user.id for i in items)


@allure.title("TC-GET-06 У нового продавца без объявлений пустой список")
def test_seller_without_items(api, fresh_user):
    resp = api.get_seller_items(fresh_user.id, fresh_user.token)
    assert resp.status_code == 200
    assert as_list(json_body(resp)) == []


@allure.title("TC-GET-07 Объявления одного продавца не попадают в список другого")
def test_seller_items_isolation(api, user, other_user, item_factory):
    mine = item_factory.create(user)
    theirs = item_factory.create(other_user)
    mine_ids = {pick(i, "id") for i in as_list(api.get_seller_items(user.id, user.token).json())}
    their_ids = {
        pick(i, "id") for i in as_list(api.get_seller_items(other_user.id, user.token).json())
    }
    assert mine.id in mine_ids and theirs.id not in mine_ids
    assert theirs.id in their_ids and mine.id not in their_ids


@allure.title("TC-GET-08 Некорректный sellerID: {bad}")
@pytest.mark.negative
@pytest.mark.parametrize("bad", ["abc", "1.5", "-1", "' OR 1=1--", "9" * 40, "%20"])
def test_seller_items_invalid_seller_id(api, user, bad):
    assert_accepted_or_rejected(api.get_seller_items(bad, user.token))


@allure.title("TC-GET-09 Строго нечисловой sellerID отклоняется 4xx")
@pytest.mark.negative
def test_seller_items_non_numeric_rejected(api, user):
    assert_client_error(api.get_seller_items("abc", user.token))


@allure.title("TC-GET-10 Несуществующий продавец: пустой список или 404, но не 5xx")
@pytest.mark.boundary
def test_seller_items_unknown_seller(api, user):
    resp = api.get_seller_items(2**31 - 1, user.token)
    assert_accepted_or_rejected(resp)
    if resp.status_code == 200:
        assert as_list(resp.json()) == []


@allure.title("TC-GET-11 Удалённое объявление пропадает из списка продавца")
def test_deleted_item_removed_from_seller_list(api, user, item_factory):
    keep = item_factory.create(user)
    gone = item_factory.create(user)
    assert api.delete_item(gone.id, user.token).status_code in (200, 204)
    ids = {pick(i, "id") for i in as_list(api.get_seller_items(user.id, user.token).json())}
    assert keep.id in ids and gone.id not in ids

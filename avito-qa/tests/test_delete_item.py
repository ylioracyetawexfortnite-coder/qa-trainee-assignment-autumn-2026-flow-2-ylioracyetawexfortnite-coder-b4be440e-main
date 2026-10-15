"""DELETE /api/2/item/{id}."""

import uuid

import allure
import pytest

from src.helpers import as_list, pick
from tests.conftest import assert_client_error

pytestmark = allure.feature("Удаление объявления")

DELETE_OK = (200, 204)


@allure.title("TC-DEL-01 Удаление объявления, после чего оно недоступно")
@pytest.mark.smoke
def test_delete_item(api, user, item_factory):
    created = item_factory.create(user)
    resp = api.delete_item(created.id, user.token)
    assert resp.status_code in DELETE_OK
    assert_client_error(api.get_item(created.id, user.token), allowed=(404,))


@allure.title("TC-DEL-02 Повторное удаление того же объявления -> 404")
@pytest.mark.negative
def test_delete_twice(api, user, item_factory):
    created = item_factory.create(user)
    assert api.delete_item(created.id, user.token).status_code in DELETE_OK
    assert_client_error(api.delete_item(created.id, user.token), allowed=(404,))


@allure.title("TC-DEL-03 Удаление несуществующего объявления -> 404")
@pytest.mark.negative
def test_delete_not_found(api, user):
    assert_client_error(api.delete_item(uuid.uuid4(), user.token), allowed=(404,))


@allure.title("TC-DEL-04 Удаление с некорректным id: {bad_id}")
@pytest.mark.negative
@pytest.mark.parametrize(
    "bad_id", ["abc", "123", "-1", "' OR '1'='1", pytest.param("a" * 300, id="300 символов"), "%20"]
)
def test_delete_invalid_id(api, user, bad_id):
    assert_client_error(api.delete_item(bad_id, user.token))


@allure.title("TC-DEL-05 Удаление одного объявления не затрагивает другие")
def test_delete_does_not_touch_others(api, fresh_user, item_factory):
    user = fresh_user
    keep = item_factory.create(user)
    gone = item_factory.create(user)
    assert api.delete_item(gone.id, user.token).status_code in DELETE_OK
    assert api.get_item(keep.id, user.token).status_code == 200
    ids = {pick(i, "id") for i in as_list(api.get_seller_items(user.id, user.token).json())}
    assert ids == {keep.id}


@allure.title("TC-DEL-06 Старой версии DELETE /api/1/item/{id} нет, объявление остаётся")
@pytest.mark.negative
def test_delete_v1_not_available(api, user, item):
    resp = api.request("DELETE", f"/api/1/item/{item.id}", token=user.token)
    assert_client_error(resp)
    assert api.get_item(item.id, user.token).status_code == 200


@allure.title("TC-DEL-07 После удаления можно создать новое объявление с теми же данными")
def test_recreate_after_delete(api, user, item_factory):
    created = item_factory.create(user, name="reusable-name", price=500)
    assert api.delete_item(created.id, user.token).status_code in DELETE_OK
    again = item_factory.create(user, name="reusable-name", price=500)
    assert again.id != created.id

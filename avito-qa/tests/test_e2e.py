"""Сквозной сценарий: регистрация -> авторизация -> создание -> чтение -> статистика -> удаление."""

import allure
import pytest

from src.helpers import (
    as_list,
    build_item_payload,
    extract_item_id,
    first,
    pick,
    unique_password,
    unique_username,
)

pytestmark = [allure.feature("E2E"), pytest.mark.e2e]


@allure.title("TC-E2E-01 Полный жизненный цикл объявления")
def test_full_item_lifecycle(api):
    username, password = unique_username("e2e"), unique_password()

    with allure.step("Регистрация"):
        reg = api.register(username, password)
        assert reg.status_code == 201
        seller_id = reg.json()["id"]

    with allure.step("Авторизация"):
        auth = api.authorize(username, password)
        assert auth.status_code == 200
        token = auth.json()["accessToken"]

    item_id = None
    try:
        with allure.step("Создание объявления"):
            payload = build_item_payload(seller_id)
            created = api.create_item(payload, token)
            assert created.status_code in (200, 201)
            item_id = extract_item_id(created)
            assert item_id

        with allure.step("Получение объявления"):
            got = api.get_item(item_id, token)
            assert got.status_code == 200
            data = first(got.json())
            assert pick(data, "name") == payload["name"]
            assert pick(data, "price") == payload["price"]
            assert pick(data, "sellerID", "sellerId") == seller_id

        with allure.step("Объявление есть в списке продавца"):
            listing = as_list(api.get_seller_items(seller_id, token).json())
            assert item_id in {pick(i, "id") for i in listing}

        with allure.step("Статистика v1 и v2"):
            for fetch in (api.stat_v1, api.stat_v2):
                resp = fetch(item_id, token)
                assert resp.status_code == 200
                stats = first(resp.json())
                for key, value in payload["statistics"].items():
                    assert stats[key] == value

        with allure.step("Удаление объявления"):
            assert api.delete_item(item_id, token).status_code in (200, 204)
            item_id = None

        with allure.step("Проверка, что объявление удалено"):
            assert api.get_item(extract_item_id(created), token).status_code == 404
            # статистика удалённого объявления проверяется отдельно: TC-STAT-06 (BUG-2)
    finally:
        if item_id:  # тест упал до удаления — возвращаем стенд в исходное состояние
            api.delete_item(item_id, token)

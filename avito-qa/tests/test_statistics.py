"""GET /api/1/statistic/{id} и GET /api/2/statistic/{id}."""

import uuid

import allure
import pytest
from jsonschema import validate

from src.config import MAX_RESPONSE_TIME
from src.helpers import build_item_payload, extract_item_id, first, json_body
from src.schemas import STATISTICS
from tests.conftest import OK_CREATE, assert_client_error

pytestmark = allure.feature("Статистика")

VERSIONS = ["v1", "v2"]


def get_stat(api, version, item_id, token):
    return api.stat_v1(item_id, token) if version == "v1" else api.stat_v2(item_id, token)


@allure.title("TC-STAT-01 Статистика {version} совпадает с отправленной при создании")
@pytest.mark.smoke
@pytest.mark.parametrize("version", VERSIONS)
def test_statistics_match_created(api, user, item, version):
    resp = get_stat(api, version, item.id, user.token)
    assert resp.status_code == 200
    stats = first(resp.json())
    validate(stats, STATISTICS)
    for key, value in item.payload["statistics"].items():
        assert stats[key] == value, f"{key}: ожидали {value}, получили {stats[key]}"


@allure.title("TC-STAT-02 Версии v1 и v2 возвращают согласованные данные")
def test_statistics_versions_consistent(api, user, item):
    v1 = first(api.stat_v1(item.id, user.token).json())
    v2 = first(api.stat_v2(item.id, user.token).json())
    assert v1 == v2


@allure.title("TC-STAT-03 Нулевая статистика сохраняется как нули ({version})")
@pytest.mark.boundary
@pytest.mark.parametrize("version", VERSIONS)
def test_statistics_zero(api, user, item_factory, version):
    zeros = {"likes": 0, "viewCount": 0, "contacts": 0}
    resp = item_factory.create_raw(user, build_item_payload(user.id, statistics=zeros))
    if resp.status_code not in OK_CREATE:
        pytest.xfail("BUG-9: нулевое значение отклоняется как «поле обязательно»")
    created_id = extract_item_id(resp)
    stats = first(get_stat(api, version, created_id, user.token).json())
    assert {k: stats[k] for k in zeros} == zeros


@allure.title("TC-STAT-04 Несуществующий id ({version}) -> 404")
@pytest.mark.negative
@pytest.mark.parametrize("version", VERSIONS)
def test_statistics_not_found(api, user, version):
    assert_client_error(get_stat(api, version, uuid.uuid4(), user.token), allowed=(404,))


@allure.title("TC-STAT-05 Некорректный id {bad_id} ({version})")
@pytest.mark.negative
@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize(
    "bad_id", ["abc", "123", "-1", "' OR '1'='1", pytest.param("a" * 300, id="300 символов")]
)
def test_statistics_invalid_id(api, user, version, bad_id):
    assert_client_error(get_stat(api, version, bad_id, user.token))


@allure.title("TC-STAT-06 После удаления объявления статистика недоступна ({version})")
@pytest.mark.xfail(reason="BUG-2: статистика удалённого объявления доступна", strict=True)
@pytest.mark.parametrize("version", VERSIONS)
def test_statistics_after_delete(api, user, item_factory, version):
    created = item_factory.create(user)
    assert api.delete_item(created.id, user.token).status_code in (200, 204)
    assert_client_error(get_stat(api, version, created.id, user.token), allowed=(404,))


@allure.title("TC-STAT-07 Повторный запрос статистики возвращает те же данные ({version})")
@pytest.mark.parametrize("version", VERSIONS)
def test_statistics_stable(api, user, item, version):
    a = json_body(get_stat(api, version, item.id, user.token))
    b = json_body(get_stat(api, version, item.id, user.token))
    assert a == b


@allure.title("TC-STAT-08 Большие значения статистики не искажаются ({version})")
@pytest.mark.boundary
@pytest.mark.parametrize("version", VERSIONS)
def test_statistics_large_values(api, user, item_factory, version):
    big = {"likes": 2147483647, "viewCount": 2147483647, "contacts": 2147483647}
    created = item_factory.create(user, statistics=big)
    stats = first(get_stat(api, version, created.id, user.token).json())
    assert {k: stats[k] for k in big} == big


@allure.title("TC-STAT-09 Несуществующая версия API (v3) отклоняется")
@pytest.mark.negative
def test_statistics_unknown_version(api, user, item):
    resp = api.request("GET", f"/api/3/statistic/{item.id}", token=user.token)
    assert_client_error(resp)


@allure.title("TC-STAT-10 Время ответа статистики не превышает порог ({version})")
@pytest.mark.nonfunctional
@pytest.mark.parametrize("version", VERSIONS)
def test_statistics_response_time(api, user, item, version):
    resp = get_stat(api, version, item.id, user.token)
    assert resp.elapsed.total_seconds() < MAX_RESPONSE_TIME

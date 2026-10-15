"""Фикстуры. Все данные создаются динамически; созданные объявления удаляются в teardown."""

import time
from dataclasses import dataclass, field

import pytest

from src.client import ApiClient, ServiceTimeout
from src.config import REGISTER_ATTEMPTS, STAND_RECOVERY_WAIT
from src.helpers import (
    build_item_payload,
    extract_item_id,
    first,
    json_body,
    unique_password,
    unique_username,
)

OK_CREATE = (200, 201)


@pytest.fixture(scope="session")
def api() -> ApiClient:
    return ApiClient()


@dataclass
class User:
    id: int
    username: str
    password: str
    token: str


def register_user(api: ApiClient) -> User:
    """Регистрация -> авторизация. Стенд общий и иногда тормозит, поэтому при таймауте
    повторяем попытку (с новым логином: прошлый запрос мог дойти до сервера)."""
    last_error = None
    for attempt in range(1, REGISTER_ATTEMPTS + 1):
        username, password = unique_username(), unique_password()
        try:
            reg = api.register(username, password)
            assert reg.status_code == 201, f"регистрация не удалась: {reg.status_code} {reg.text}"
            auth = api.authorize(username, password)
            assert (
                auth.status_code == 200
            ), f"авторизация не удалась: {auth.status_code} {auth.text}"
            return User(reg.json()["id"], username, password, auth.json()["accessToken"])
        except ServiceTimeout as e:  # повторяем только таймауты
            last_error = e
            time.sleep(2 * attempt)
    raise last_error


def wait_for_stand(api: ApiClient, user: User) -> float:
    """Ждёт, пока стенд снова начнёт отвечать на запись (создать + удалить объявление).
    Возвращает, сколько секунд ждали. Если стенд не ожил за STAND_RECOVERY_WAIT — прерывает прогон.
    """
    started = time.monotonic()
    while time.monotonic() - started < STAND_RECOVERY_WAIT:
        try:
            resp = api.request(
                "POST",
                "/api/1/item",
                token=user.token,
                json=build_item_payload(user.id),
                timeout=8,
            )
            if resp.status_code in OK_CREATE:
                item_id = extract_item_id(resp)
                if item_id:
                    api.delete_item(item_id, user.token)
                api.degraded = False
                return time.monotonic() - started
        except ServiceTimeout:
            pass
        time.sleep(5)
    pytest.exit(
        f"Стенд не отвечает на POST /api/1/item уже {STAND_RECOVERY_WAIT:.0f} с, "
        "прогон остановлен. Запустите позже или увеличьте STAND_RECOVERY_WAIT.",
        returncode=2,
    )


@pytest.fixture(autouse=True)
def _stand_guard(request, api):
    """После таймаута следующий тест не стартует, пока стенд не оживёт. Так одно зависание
    не превращается в серию ложных падений у соседних тестов: красным остаётся только тот
    тест, который реально упёрся в зависание."""
    if api.degraded:
        waited = wait_for_stand(api, request.getfixturevalue("shared_user"))
        print(f"\n[stand-guard] после таймаута ждали восстановления стенда {waited:.0f} с")
    yield


@pytest.fixture
def user_factory(api):
    """Создаёт нового пользователя: регистрация -> авторизация."""
    return lambda: register_user(api)


@pytest.fixture(scope="session")
def shared_user(api) -> User:
    """Один пользователь на весь прогон: снижает нагрузку на общий стенд.
    Тесты с ним не должны полагаться на чистый список объявлений."""
    return register_user(api)


@pytest.fixture
def user(shared_user) -> User:
    return shared_user


@pytest.fixture
def fresh_user(user_factory) -> User:
    """Новый пользователь без объявлений, для тестов, проверяющих точный состав списка."""
    return user_factory()


@pytest.fixture
def other_user(user_factory) -> User:
    return user_factory()


@dataclass
class Item:
    id: str
    payload: dict
    owner: User


@dataclass
class ItemFactory:
    api: ApiClient
    _created: list = field(default_factory=list)

    def create_raw(self, owner: User, payload):
        """Отправляет POST как есть. Если объявление всё же создалось — оно попадёт в cleanup."""
        resp = self.api.create_item(payload, owner.token)
        item_id = extract_item_id(resp)
        if item_id and resp.status_code in OK_CREATE:
            self._created.append((item_id, owner))
        return resp

    def create(self, owner: User, **overrides) -> Item:
        payload = build_item_payload(owner.id, **overrides)
        resp = self.create_raw(owner, payload)
        assert (
            resp.status_code in OK_CREATE
        ), f"объявление не создано: {resp.status_code} {resp.text}"
        item_id = extract_item_id(resp)
        assert item_id, f"в ответе нет UUID: {resp.text}"
        return Item(item_id, payload, owner)

    def cleanup(self):
        for item_id, owner in reversed(self._created):
            try:
                self.api.delete_item(item_id, owner.token)
            except Exception:  # уборка не должна ронять тест
                pass


@pytest.fixture
def item_factory(api):
    factory = ItemFactory(api)
    yield factory
    factory.cleanup()


@pytest.fixture
def item(item_factory, user) -> Item:
    return item_factory.create(user)


# ---------- общие проверки ----------
def assert_client_error(resp, allowed: tuple | None = None):
    """Ожидаем 4xx (или конкретный набор кодов) и отсутствие 5xx."""
    assert resp.status_code < 500, f"серверная ошибка {resp.status_code}: {resp.text[:300]}"
    if allowed:
        assert resp.status_code in allowed, f"ожидали {allowed}, получили {resp.status_code}"
    else:
        assert (
            400 <= resp.status_code < 500
        ), f"ожидали 4xx, получили {resp.status_code}: {resp.text[:300]}"


def assert_accepted_or_rejected(resp):
    """Для спорных граничных значений: либо принято (2xx), либо отклонено 4xx, но не 5xx."""
    assert resp.status_code < 500, f"серверная ошибка {resp.status_code}: {resp.text[:300]}"
    assert resp.status_code in (200, 201) or 400 <= resp.status_code < 500, resp.status_code


def read_item(api, item_id, token) -> dict:
    resp = api.get_item(item_id, token)
    assert resp.status_code == 200, f"GET item: {resp.status_code} {resp.text[:300]}"
    data = json_body(resp)
    assert data is not None, "ответ не JSON"
    return first(data)


# ---------- таймаут не должен прятаться за xfail ----------
@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    """xfail ловит любое исключение, поэтому зависание стенда выглядело бы как «ожидаемый дефект».
    Если тест помечен xfail и упал именно из-за таймаута, показываем это как настоящее падение.
    Исключение: BUG-5, где зависание и есть ожидаемый дефект."""
    outcome = yield
    rep = outcome.get_result()
    if (
        call.when == "call"
        and call.excinfo is not None
        and call.excinfo.errisinstance(ServiceTimeout)
        and getattr(rep, "wasxfail", None)
        and "BUG-5" not in rep.wasxfail
    ):
        rep.outcome = "failed"
        rep.wasxfail = None
        del rep.wasxfail

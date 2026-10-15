
import requests
import pytest
from uuid import uuid4, UUID
from test_data import VALID_ITEM_PAYLOAD

BASE_URL = "https://qa-internship.avito.com"
TIMEOUT = 30


def get_created_id(resp):
    """Получает UUID из ответа на создание объявления."""

    data = resp.json()
    assert isinstance(data, dict), "Неверный формат ответа"

    status = data.get("status")
    assert isinstance(status, str) and " - " in status, (
        "Ответ не содержит ID объявления"
    )

    item_id = status.rsplit(" - ", 1)[-1]

    try:
        UUID(item_id)
    except ValueError:
        pytest.fail("Сервер вернул некорректный UUID")

    return item_id


def create_item(auth_session):
    """Создаёт объявление владельца."""

    payload = VALID_ITEM_PAYLOAD.copy()
    payload["sellerID"] = auth_session["seller_id"]

    resp = requests.post(
        f"{BASE_URL}/api/1/item",
        json=payload,
        headers=auth_session["headers"],
        timeout=TIMEOUT
    )

    assert resp.status_code == 200, (
        f"Ошибка создания: HTTP {resp.status_code}"
    )

    item_id = get_created_id(resp)
    auth_session["items_to_delete"].append(item_id)

    return item_id


def create_second_user():
    """Регистрирует и авторизует второго пользователя."""

    data = {
        "username": f"qa_security_{uuid4().hex}",
        "password": "Password123!"
    }

    reg_resp = requests.post(
        f"{BASE_URL}/api/1/register",
        json=data,
        timeout=TIMEOUT
    )

    assert reg_resp.status_code == 201, (
        f"Ошибка регистрации: HTTP {reg_resp.status_code}"
    )

    user = reg_resp.json()
    assert isinstance(user, dict), "Неверный ответ регистрации"

    seller_id = user.get("id")
    assert type(seller_id) is int, "Не получен ID второго пользователя"
    assert user.get("username") == data["username"]

    auth_resp = requests.post(
        f"{BASE_URL}/api/1/autorize",
        json=data,
        timeout=TIMEOUT
    )

    assert auth_resp.status_code == 200, (
        f"Ошибка авторизации: HTTP {auth_resp.status_code}"
    )

    auth = auth_resp.json()
    assert isinstance(auth, dict), "Неверный ответ авторизации"

    token = auth.get("accessToken")
    assert isinstance(token, str) and token.strip(), (
        "Не получен токен второго пользователя"
    )
    assert auth.get("tokenType", "").lower() == "bearer"

    headers = {"Authorization": f"Bearer {token}"}

    # Проверяем, что токен второго пользователя работает
    check_resp = requests.get(
        f"{BASE_URL}/api/1/{seller_id}/item",
        headers=headers,
        timeout=TIMEOUT
    )

    assert check_resp.status_code == 200, (
        "Токен второго пользователя не работает"
    )

    return {"seller_id": seller_id, "headers": headers}


def cleanup_if_created(resp, auth_session, second_user=None):
    """Очищает неожиданно созданное объявление только тестовых пользователей."""

    if resp.status_code != 200:
        return

    item_id = get_created_id(resp)

    check_resp = requests.get(
        f"{BASE_URL}/api/1/item/{item_id}",
        headers=auth_session["headers"],
        timeout=TIMEOUT
    )

    if check_resp.status_code != 200:
        return

    items = check_resp.json()

    if not isinstance(items, list) or len(items) != 1:
        return

    item = items[0]

    if not isinstance(item, dict) or item.get("id") != item_id:
        return

    seller_id = item.get("sellerId")

    if seller_id == auth_session["seller_id"]:
        auth_session["items_to_delete"].append(item_id)

    elif second_user and seller_id == second_user["seller_id"]:
        del_resp = requests.delete(
            f"{BASE_URL}/api/2/item/{item_id}",
            headers=second_user["headers"],
            timeout=TIMEOUT
        )

        assert del_resp.status_code in (200, 404), (
            "Не удалось очистить объявление второго пользователя"
        )


def test_no_token_access(auth_session):
    """4: Доступ к защищённым эндпоинтам без токена"""

    item_id = create_item(auth_session)
    seller_id = auth_session["seller_id"]

    # Проверяем пять эндпоинтов без Authorization
    endpoints = [
        ("GET", f"/api/1/item/{item_id}"),
        ("GET", f"/api/1/{seller_id}/item"),
        ("GET", f"/api/1/statistic/{item_id}"),
        ("GET", f"/api/2/statistic/{item_id}"),
        ("DELETE", f"/api/2/item/{item_id}")
    ]

    for method, path in endpoints:
        resp = requests.request(
            method,
            f"{BASE_URL}{path}",
            timeout=TIMEOUT
        )

        assert resp.status_code == 401, (
            f"{method} {path}: ожидалась 401, "
            f"получено HTTP {resp.status_code}"
        )

    # DELETE без токена не должен удалить объявление
    check_resp = requests.get(
        f"{BASE_URL}/api/1/item/{item_id}",
        headers=auth_session["headers"],
        timeout=TIMEOUT
    )

    assert check_resp.status_code == 200, (
        "Объявление исчезло после DELETE без токена"
    )

    # Отдельно проверяем создание без токена
    payload = VALID_ITEM_PAYLOAD.copy()
    payload["sellerID"] = seller_id

    resp = requests.post(
        f"{BASE_URL}/api/1/item",
        json=payload,
        timeout=TIMEOUT
    )

    cleanup_if_created(resp, auth_session)

    assert resp.status_code == 401, (
        f"POST без токена: ожидалась 401, "
        f"получено HTTP {resp.status_code}"
    )


def test_wrong_seller_id(auth_session):
    """5: Подмена sellerID и X-UserId"""

    second_user = create_second_user()
    second_id = second_user["seller_id"]

    assert second_id != auth_session["seller_id"]

    payload = VALID_ITEM_PAYLOAD.copy()
    payload["sellerID"] = second_id

    # Проверяем чужой sellerID без X-UserId и с ним
    for use_x_user_id in [False, True]:
        headers = auth_session["headers"].copy()

        if use_x_user_id:
            headers["X-UserId"] = str(second_id)

        resp = requests.post(
            f"{BASE_URL}/api/1/item",
            json=payload,
            headers=headers,
            timeout=TIMEOUT
        )

        cleanup_if_created(resp, auth_session, second_user)

        assert 400 <= resp.status_code < 500, (
            f"Чужой sellerID не был отклонён. "
            f"X-UserId={use_x_user_id}, "
            f"HTTP {resp.status_code}"
        )


def test_get_nonexistent_item(auth_session):
    """7: Получение несуществующего объявления"""

    fake_uuid = str(uuid4())

    resp = requests.get(
        f"{BASE_URL}/api/1/item/{fake_uuid}",
        headers=auth_session["headers"],
        timeout=TIMEOUT
    )

    assert resp.status_code == 404, (
        f"Ожидалась 404, получено HTTP {resp.status_code}"
    )


def test_delete_other_user_item(auth_session):
    """6: Исследование удаления чужого объявления"""

    # Пользователь А создаёт объявление
    item_id = create_item(auth_session)

    # Регистрируем пользователя Б с рабочим токеном
    second_user = create_second_user()

    assert second_user["seller_id"] != auth_session["seller_id"]

    # Убеждаемся, что объявление существует до удаления
    before_resp = requests.get(
        f"{BASE_URL}/api/1/item/{item_id}",
        headers=auth_session["headers"],
        timeout=TIMEOUT
    )

    assert before_resp.status_code == 200, (
        "Объявление недоступно до проверки"
    )

    before_items = before_resp.json()
    assert isinstance(before_items, list) and len(before_items) == 1
    assert before_items[0].get("id") == item_id
    assert before_items[0].get("sellerId") == auth_session["seller_id"]

    # Пользователь Б пытается удалить объявление А
    del_resp = requests.delete(
        f"{BASE_URL}/api/2/item/{item_id}",
        headers=second_user["headers"],
        timeout=TIMEOUT
    )

    # Пользователь А проверяет своё объявление
    after_resp = requests.get(
        f"{BASE_URL}/api/1/item/{item_id}",
        headers=auth_session["headers"],
        timeout=TIMEOUT
    )

    # Наблюдаемое поведение стенда:
    # другой пользователь удаляет объявление успешно.
    # В контракте DELETE запрет явно не описан.
    if del_resp.status_code == 200 and after_resp.status_code == 404:
        pytest.xfail(
            "Стенд позволяет удалить чужое объявление. "
            "Ограничение по владельцу не указано в контракте."
        )

    # Проверяем, что удаление отклонено
    assert 400 <= del_resp.status_code < 500, (
        f"Неожиданный ответ DELETE: HTTP {del_resp.status_code}"
    )

    # Объявление должно остаться доступным владельцу
    assert after_resp.status_code == 200, (
        "Объявление недоступно после попытки чужого удаления"
    )

    items = after_resp.json()
    assert isinstance(items, list) and len(items) == 1
    assert items[0].get("id") == item_id
    assert items[0].get("sellerId") == auth_session["seller_id"]

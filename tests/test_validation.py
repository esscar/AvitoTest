
import pytest
import requests
from uuid import UUID
from test_data import VALID_ITEM_PAYLOAD, INVALID_PRICES

BASE_URL = "https://qa-internship.avito.com"
TIMEOUT = 30


def create_item(auth_session, payload):
    """Отправляет POST и записывает созданное объявление для очистки."""

    resp = requests.post(
        f"{BASE_URL}/api/1/item",
        json=payload,
        headers=auth_session["headers"],
        timeout=TIMEOUT
    )

    item_id = None

    if 200 <= resp.status_code < 300:
        data = resp.json()
        assert isinstance(data, dict), "Неверный ответ создания"

        status = data.get("status")
        prefix = "Сохранили объявление - "

        assert isinstance(status, str) and status.startswith(prefix), (
            "В ответе создания отсутствует ID объявления"
        )

        item_id = status[len(prefix):]

        try:
            UUID(item_id)
        except (TypeError, ValueError, AttributeError):
            pytest.fail("Сервер вернул некорректный UUID")

        auth_session["items_to_delete"].append(item_id)

    return resp, item_id


def check_saved_item(auth_session, item_id, payload):
    """Проверяет сохранённое объявление через GET."""

    resp = requests.get(
        f"{BASE_URL}/api/1/item/{item_id}",
        headers=auth_session["headers"],
        timeout=TIMEOUT
    )

    assert resp.status_code == 200, (
        "Созданное объявление недоступно"
    )

    items = resp.json()
    assert isinstance(items, list) and len(items) == 1, (
        "Неверный формат ответа GET объявления"
    )

    item = items[0]
    assert isinstance(item, dict), "Неверный формат объявления"

    assert item.get("id") == item_id, "Неверный ID объявления"
    assert item.get("sellerId") == auth_session["seller_id"], (
        "Неверный ID продавца"
    )

    if "name" in payload:
        assert isinstance(item.get("name"), str), (
            "Название объявления должно быть строкой"
        )

    if type(payload.get("price")) is int:
        assert item.get("price") == payload["price"], (
            "Цена объявления отличается от отправленной"
        )


@pytest.mark.parametrize("invalid_price", INVALID_PRICES)
def test_create_item_invalid_price(auth_session, invalid_price):
    """8, 9: Отрицательная, нулевая и очень большая цена."""

    payload = VALID_ITEM_PAYLOAD.copy()
    payload["sellerID"] = auth_session["seller_id"]
    payload["price"] = invalid_price

    resp, item_id = create_item(auth_session, payload)

    assert resp.status_code in (200, 400), (
        f"Неожиданный статус для цены {invalid_price}: "
        f"HTTP {resp.status_code}"
    )

    if item_id:
        check_saved_item(auth_session, item_id, payload)


def test_create_item_missing_fields(auth_session):
    """12: Создание объявления без поля name."""

    payload = VALID_ITEM_PAYLOAD.copy()
    payload["sellerID"] = auth_session["seller_id"]
    del payload["name"]

    resp, item_id = create_item(auth_session, payload)

    assert resp.status_code in (200, 400), (
        f"Неожиданный статус без name: HTTP {resp.status_code}"
    )

    if item_id:
        check_saved_item(auth_session, item_id, payload)


@pytest.mark.parametrize("field,value", [
    ("price", "пять тысяч"),
    ("sellerID", "admin"),
])
def test_create_item_wrong_types(auth_session, field, value):
    """11: Некорректные типы полей price и sellerID."""

    payload = VALID_ITEM_PAYLOAD.copy()
    payload["sellerID"] = auth_session["seller_id"]
    payload[field] = value

    resp, _ = create_item(auth_session, payload)

    assert resp.status_code == 400, (
        f"Поле {field} с неверным типом принято: "
        f"HTTP {resp.status_code}"
    )


def test_create_item_negative_statistics(auth_session):
    """10: Отрицательные значения счётчиков статистики."""

    payload = VALID_ITEM_PAYLOAD.copy()
    payload["sellerID"] = auth_session["seller_id"]
    payload["statistics"] = {
        "contacts": -5,
        "likes": -1,
        "viewCount": -10
    }

    resp, item_id = create_item(auth_session, payload)

    assert resp.status_code in (200, 400), (
        f"Неожиданный статус для отрицательной статистики: "
        f"HTTP {resp.status_code}"
    )

    if item_id:
        check_saved_item(auth_session, item_id, payload)


def test_create_item_missing_statistics(auth_session):
    """14: Создание без блока statistics."""

    payload = VALID_ITEM_PAYLOAD.copy()
    payload["sellerID"] = auth_session["seller_id"]
    del payload["statistics"]

    resp, item_id = create_item(auth_session, payload)

    assert resp.status_code in (200, 400), (
        f"Неожиданный статус без statistics: "
        f"HTTP {resp.status_code}"
    )

    if item_id:
        check_saved_item(auth_session, item_id, payload)


def test_create_item_long_name(auth_session):
    """13: Название длиной 10 000 символов."""

    payload = VALID_ITEM_PAYLOAD.copy()
    payload["sellerID"] = auth_session["seller_id"]
    payload["name"] = "A" * 10000

    resp, item_id = create_item(auth_session, payload)

    assert resp.status_code in (200, 400), (
        f"Неожиданный статус для длинного названия: "
        f"HTTP {resp.status_code}"
    )

    if item_id:
        check_saved_item(auth_session, item_id, payload)


def test_create_item_xss(auth_session):
    """15: Проверка обработки строки, похожей на XSS."""

    payload = VALID_ITEM_PAYLOAD.copy()
    payload["sellerID"] = auth_session["seller_id"]
    payload["name"] = "<script>alert('XSS')</script>"

    resp, item_id = create_item(auth_session, payload)

    assert resp.status_code in (200, 400), (
        f"Неожиданный статус для XSS-строки: "
        f"HTTP {resp.status_code}"
    )

    if item_id:
        check_saved_item(auth_session, item_id, payload)

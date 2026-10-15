
import requests
import pytest
from uuid import UUID
from math import isfinite
from test_data import VALID_ITEM_PAYLOAD

BASE_URL = "https://qa-internship.avito.com"


def create_item(auth_session, payload):
    """Создаёт объявление и сохраняет ID для очистки."""

    resp = requests.post(
        f"{BASE_URL}/api/1/item",
        json=payload,
        headers=auth_session["headers"],
        timeout=15
    )

    assert resp.status_code == 200, (
        f"Ошибка создания: HTTP {resp.status_code}"
    )

    data = resp.json()
    assert isinstance(data, dict), "Неверный ответ создания"

    status = data.get("status")
    assert isinstance(status, str) and " - " in status, (
        "Ответ создания не содержит ID объявления"
    )

    item_id = status.rsplit(" - ", 1)[-1]

    try:
        UUID(item_id)
    except ValueError:
        pytest.fail("Сервер вернул некорректный UUID")

    auth_session["items_to_delete"].append(item_id)
    return item_id


def test_e2e_item_lifecycle(auth_session):
    """1: Полный жизненный цикл объявления"""

    payload = VALID_ITEM_PAYLOAD.copy()
    payload["sellerID"] = auth_session["seller_id"]

    # Создаём объявление
    item_id = create_item(auth_session, payload)

    # Получаем объявление
    get_resp = requests.get(
        f"{BASE_URL}/api/1/item/{item_id}",
        headers=auth_session["headers"],
        timeout=15
    )

    assert get_resp.status_code == 200

    items = get_resp.json()
    assert isinstance(items, list), "Ожидался массив объявлений"
    assert len(items) == 1, "Должно вернуться одно объявление"

    item = items[0]
    assert isinstance(item, dict), "Неверный формат объявления"
    assert item.get("id") == item_id, "Неверный ID объявления"
    assert item.get("sellerId") == payload["sellerID"], "Неверный продавец"
    assert item.get("name") == payload["name"], "Неверное название"
    assert item.get("price") == payload["price"], "Неверная цена"

    # Удаляем объявление
    del_resp = requests.delete(
        f"{BASE_URL}/api/2/item/{item_id}",
        headers=auth_session["headers"],
        timeout=15
    )

    assert del_resp.status_code == 200

    # Проверяем, что объявление удалено
    get_deleted_resp = requests.get(
        f"{BASE_URL}/api/1/item/{item_id}",
        headers=auth_session["headers"],
        timeout=15
    )

    assert get_deleted_resp.status_code == 404, (
        "Удалённое объявление всё ещё доступно"
    )

    auth_session["items_to_delete"].remove(item_id)


def test_get_all_seller_items(auth_session):
    """2: Получение всех объявлений продавца"""

    payload = VALID_ITEM_PAYLOAD.copy()
    payload["sellerID"] = auth_session["seller_id"]

    # Создаём два объявления с одинаковыми данными
    id1 = create_item(auth_session, payload)
    id2 = create_item(auth_session, payload)

    assert id1 != id2, "Объявления получили одинаковые UUID"

    # Получаем список объявлений продавца
    get_resp = requests.get(
        f"{BASE_URL}/api/1/{auth_session['seller_id']}/item",
        headers=auth_session["headers"],
        timeout=15
    )

    assert get_resp.status_code == 200

    items = get_resp.json()
    assert isinstance(items, list), "Ожидался массив объявлений"
    assert all(isinstance(item, dict) for item in items), (
        "Массив содержит некорректные данные"
    )

    # Проверяем оба созданных объявления
    for item_id in [id1, id2]:
        found = [item for item in items if item.get("id") == item_id]

        assert len(found) == 1, (
            f"Объявление {item_id} отсутствует или дублируется"
        )

        item = found[0]

        assert item.get("sellerId") == payload["sellerID"], (
            "Неверный продавец"
        )
        assert item.get("name") == payload["name"], (
            "Неверное название"
        )
        assert item.get("price") == payload["price"], (
            "Неверная цена"
        )

    # Проверяем, что все объявления принадлежат продавцу
    assert all(
        item.get("sellerId") == auth_session["seller_id"]
        for item in items
    ), "В списке обнаружены объявления другого продавца"


def test_statistics_v1_vs_v2(auth_session):
    """3: Проверка статистики v1 и v2"""

    payload = VALID_ITEM_PAYLOAD.copy()
    payload["sellerID"] = auth_session["seller_id"]

    # Создаём объявление
    item_id = create_item(auth_session, payload)

    # Проверяем обе версии статистики
    for version in [1, 2]:
        stat_resp = requests.get(
            f"{BASE_URL}/api/{version}/statistic/{item_id}",
            headers=auth_session["headers"],
            timeout=15
        )

        assert stat_resp.status_code == 200, (
            f"Ошибка статистики v{version}: HTTP {stat_resp.status_code}"
        )

        data = stat_resp.json()

        # Статистика v1 должна возвращать массив
        if version == 1:
            assert isinstance(data, list), (
                "Статистика v1 должна возвращаться массивом"
            )

        assert isinstance(data, (list, dict)), (
            f"Неверный формат статистики v{version}"
        )

        stats = data if isinstance(data, list) else [data]
        assert stats, "Статистика не должна быть пустой"

        for item in stats:
            assert isinstance(item, dict), (
                "Неверный формат статистики"
            )

            for field in ["contacts", "likes", "viewCount"]:
                assert field in item, (
                    f"Отсутствует поле {field} в статистике v{version}"
                )

                value = item[field]

                assert type(value) is int or (
                    type(value) is float and isfinite(value)
                ), (
                    f"Некорректное значение {field} "
                    f"в статистике v{version}"
                )

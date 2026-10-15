
import pytest
import requests
import time

BASE_URL = "https://qa-internship.avito.com"


@pytest.fixture(scope="function")
def auth_session():
    """Создает пользователя, получает токен и удаляет тестовые объявления."""

    # Генерация уникальных данных
    username = f"qa_student_{time.time_ns()}"
    password = "AutoPassword123!"
    data = {"username": username, "password": password}

    # Регистрация
    reg_resp = requests.post(
        f"{BASE_URL}/api/1/register",
        json=data,
        timeout=15
    )

    assert reg_resp.status_code == 201, (
        f"Ошибка регистрации: HTTP {reg_resp.status_code}"
    )

    user = reg_resp.json()
    assert isinstance(user, dict), "Неверный ответ регистрации"

    seller_id = user.get("id")
    assert type(seller_id) is int, "Не получен корректный seller_id"
    assert user.get("username") == username, "Неверный username"

    # Авторизация
    auth_resp = requests.post(
        f"{BASE_URL}/api/1/autorize",
        json=data,
        timeout=15
    )

    assert auth_resp.status_code == 200, (
        f"Ошибка авторизации: HTTP {auth_resp.status_code}"
    )

    auth = auth_resp.json()
    assert isinstance(auth, dict), "Неверный ответ авторизации"

    token = auth.get("accessToken")
    assert isinstance(token, str) and token.strip(), "Токен не получен"

    token_type = auth.get("tokenType")
    assert isinstance(token_type, str) and token_type.lower() == "bearer", (
        "Неверный тип токена"
    )

    headers = {"Authorization": f"Bearer {token}"}

    # Данные для автотестов
    session_data = {
        "headers": headers,
        "seller_id": seller_id,
        "items_to_delete": []
    }

    yield session_data

    # Очистка созданных объявлений
    errors = []

    for item_id in session_data["items_to_delete"]:
        try:
            resp = requests.delete(
                f"{BASE_URL}/api/2/item/{item_id}",
                headers=headers,
                timeout=15
            )

            if resp.status_code not in (200, 404):
                errors.append(f"{item_id}: HTTP {resp.status_code}")

        except requests.RequestException:
            errors.append(f"{item_id}: ошибка соединения")

    assert not errors, f"Ошибки очистки: {', '.join(errors)}"

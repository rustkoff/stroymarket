import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.main import COOKIE_NAME, create_app


@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path / "test.db", cookie_secure=False)


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


def register(client, email="buyer@example.ru", password="safe-password-123", name="Покупатель"):
    return client.post(
        "/api/auth/register",
        json={"name": name, "email": email, "password": password},
    )


def test_catalog_has_15_complete_products_and_uses_slug_images(client):
    response = client.get("/api/products")

    assert response.status_code == 200
    products = response.json()
    assert len(products) == 15
    assert {"cement", "plaster", "putty", "tile", "laminate", "paint", "brick", "block", "insulation", "drywall", "adhesive", "sand", "gravel", "primer", "plywood"} == {
        product["id"] for product in products
    }
    for product in products:
        assert set(product) == {"id", "name", "category", "price", "unit", "coverage", "description", "image", "specs"}
        assert isinstance(product["price"], int) and product["price"] > 0
        assert product["image"] == f"/assets/products/{product['id']}.svg"
        assert isinstance(product["specs"], dict)


def test_product_detail_and_missing_product(client):
    response = client.get("/api/products/cement")
    assert response.status_code == 200
    assert response.json()["name"] == "Цемент М500"

    assert client.get("/api/products/missing").status_code == 404
    injection = client.get("/api/products/cement' OR 1=1 --")
    assert injection.status_code in {404, 422}


def test_registration_hashes_password_and_sets_secure_session_cookie(client, app):
    response = register(client)

    assert response.status_code == 201
    assert response.json() == {"id": 1, "name": "Покупатель", "email": "buyer@example.ru"}
    cookie = response.cookies.get(COOKIE_NAME)
    assert cookie and len(cookie) >= 40
    cookie_header = response.headers["set-cookie"].lower()
    assert "httponly" in cookie_header
    assert "samesite=strict" in cookie_header
    assert "secure" not in cookie_header
    with sqlite3.connect(app.state.database_path) as connection:
        password_hash = connection.execute("SELECT password_hash FROM users").fetchone()[0]
        saved_session = connection.execute("SELECT token_hash FROM sessions").fetchone()[0]
    assert password_hash != "safe-password-123"
    assert password_hash.startswith("$argon2")
    assert saved_session != cookie
    assert client.get("/api/auth/me").json()["email"] == "buyer@example.ru"


def test_registration_normalizes_email_and_rejects_duplicate_or_invalid_input(client):
    response = register(client, email="  Buyer@Example.RU  ")
    assert response.status_code == 201
    assert response.json()["email"] == "buyer@example.ru"

    duplicate = register(client, email="BUYER@example.ru")
    assert duplicate.status_code == 409
    assert client.post(
        "/api/auth/register", json={"email": "not-an-email", "password": "short"}
    ).status_code == 422


def test_login_me_and_logout(client):
    register(client)
    client.post("/api/auth/logout")

    assert client.get("/api/auth/me").status_code == 401
    assert client.post(
        "/api/auth/login", json={"email": "BUYER@example.ru", "password": "safe-password-123"}
    ).status_code == 200
    assert client.get("/api/auth/me").status_code == 200
    assert client.post(
        "/api/auth/login", json={"email": "buyer@example.ru", "password": "wrong-password"}
    ).status_code == 401

    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_cart_requires_auth_validates_quantity_and_returns_total(client):
    assert client.get("/api/cart").status_code == 401
    register(client)
    assert client.put("/api/cart/cement", json={"quantity": 0}).status_code == 422
    assert client.put("/api/cart/cement", json={"quantity": 1000}).status_code == 422
    assert client.put("/api/cart/cement", json={"quantity": True}).status_code == 422
    assert client.put("/api/cart/missing", json={"quantity": 1}).status_code == 404

    assert client.put("/api/cart/cement", json={"quantity": 2}).json() == {
        "product_id": "cement", "quantity": 2
    }
    client.put("/api/cart/paint", json={"quantity": 1})
    client.put("/api/cart/cement", json={"quantity": 3})
    cart = client.get("/api/cart").json()
    assert [item["product"]["id"] for item in cart["items"]] == ["cement", "paint"]
    assert [item["quantity"] for item in cart["items"]] == [3, 1]
    assert cart["total"] == 3 * 489 + 1490

    assert client.delete("/api/cart/cement").status_code == 204
    cart = client.get("/api/cart").json()
    assert [item["product"]["id"] for item in cart["items"]] == ["paint"]


def test_cart_is_persisted_and_isolated_between_users(client):
    register(client)
    client.put("/api/cart/brick", json={"quantity": 5})
    client.post("/api/auth/logout")

    register(client, email="second@example.ru", name="Второй покупатель")
    assert client.get("/api/cart").json() == {"items": [], "total": 0}
    client.post("/api/auth/logout")

    client.post("/api/auth/login", json={"email": "buyer@example.ru", "password": "safe-password-123"})
    cart = client.get("/api/cart").json()
    assert cart["items"][0]["product"]["id"] == "brick"
    assert cart["items"][0]["quantity"] == 5
    assert cart["total"] == 120


def test_contact_message_is_validated_and_saved(client, app):
    response = client.post(
        "/api/contact",
        json={"name": "  Иван  ", "email": " IVAN@example.ru ", "message": "  Нужна консультация  "},
    )
    assert response.status_code == 201
    assert response.json()["message"] == "Сообщение отправлено"
    with sqlite3.connect(app.state.database_path) as connection:
        row = connection.execute("SELECT name, email, message FROM contact_messages").fetchone()
    assert row == ("Иван", "ivan@example.ru", "Нужна консультация")
    assert client.post(
        "/api/contact", json={"name": "", "email": "invalid", "message": "x"}
    ).status_code == 422


def test_secure_cookie_can_be_enabled_for_production(tmp_path):
    secure_app = create_app(tmp_path / "secure.db", cookie_secure=True)
    with TestClient(secure_app) as secure_client:
        response = register(secure_client)
    assert "secure" in response.headers["set-cookie"].lower()


def test_frontend_is_served_from_root_after_api_routes(tmp_path):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text("<h1>Stroymarket</h1>", encoding="utf-8")
    frontend_app = create_app(tmp_path / "frontend-test.db", frontend_dir=frontend)

    with TestClient(frontend_app) as frontend_client:
        assert "Stroymarket" in frontend_client.get("/").text
        assert frontend_client.get("/api/products").status_code == 200

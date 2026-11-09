"""FastAPI application for the Stroymarket store."""

import hashlib
import json
import os
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pwdlib import PasswordHash

from backend.database import connect, initialize_database
from backend.schemas import CartUpdate, ContactMessage, Credentials, Registration

ROOT = Path(__file__).resolve().parent.parent
COOKIE_NAME = "stroymarket_session"
SESSION_MAX_AGE = 30 * 24 * 60 * 60
password_hasher = PasswordHash.recommended()


def product_from_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "category": row["category"],
        "price": row["price"],
        "unit": row["unit"],
        "coverage": row["coverage"],
        "description": row["description"],
        "image": row["image"],
        "specs": json.loads(row["specs"]),
    }


def public_user(row: sqlite3.Row) -> dict:
    return {"id": row["id"], "name": row["name"], "email": row["email"]}


def create_app(
    database_path: str | Path | None = None,
    *,
    cookie_secure: bool | None = None,
    frontend_dir: str | Path | None = None,
) -> FastAPI:
    db_path = Path(database_path or os.getenv("DATABASE_PATH", "data/store.db")).resolve()
    secure_cookie = (
        os.getenv("COOKIE_SECURE", "false").strip().lower() in {"1", "true", "yes"}
        if cookie_secure is None
        else cookie_secure
    )
    web_dir = Path(frontend_dir) if frontend_dir is not None else ROOT / "frontend"

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        initialize_database(db_path)
        yield

    app = FastAPI(title="Stroymarket API", version="1.0.0", lifespan=lifespan)
    app.state.database_path = db_path
    app.state.cookie_secure = secure_cookie

    @app.middleware("http")
    async def reject_cross_origin_mutations(request: Request, call_next):
        origin = request.headers.get("origin")
        if origin and request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.url.path.startswith("/api/"):
            try:
                source = urlsplit(origin)
                target = request.url
                source_port = source.port or (443 if source.scheme == "https" else 80)
                target_port = target.port or (443 if target.scheme == "https" else 80)
                same_origin = (
                    source.scheme in {"http", "https"}
                    and source.hostname is not None
                    and source.username is None
                    and source.password is None
                    and source.path in {"", "/"}
                    and not source.query
                    and not source.fragment
                    and (source.scheme, source.hostname.lower(), source_port)
                    == (target.scheme, target.hostname.lower(), target_port)
                )
            except ValueError:
                same_origin = False
            if not same_origin:
                return JSONResponse(status_code=403, content={"detail": "Cross-origin request is not allowed"})
        return await call_next(request)

    def get_current_user(request: Request) -> dict:
        token = request.cookies.get(COOKIE_NAME)
        if not token:
            raise HTTPException(status_code=401, detail="Требуется авторизация")
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with connect(db_path) as connection:
            row = connection.execute(
                """SELECT users.id, users.name, users.email
                   FROM sessions JOIN users ON users.id = sessions.user_id
                   WHERE sessions.token_hash = ? AND sessions.expires_at > ?""",
                (token_hash, int(time.time())),
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=401, detail="Требуется авторизация")
        return public_user(row)

    authenticated_user = Annotated[dict, Depends(get_current_user)]

    @app.get("/api/products")
    def list_products() -> list[dict]:
        with connect(db_path) as connection:
            rows = connection.execute(
                "SELECT id, name, category, price, unit, coverage, description, image, specs FROM products ORDER BY rowid"
            ).fetchall()
        return [product_from_row(row) for row in rows]

    @app.get("/api/products/{product_id}")
    def get_product(product_id: str) -> dict:
        with connect(db_path) as connection:
            row = connection.execute(
                """SELECT id, name, category, price, unit, coverage, description, image, specs
                   FROM products WHERE id = ?""",
                (product_id,),
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Товар не найден")
        return product_from_row(row)

    @app.post("/api/auth/register", status_code=status.HTTP_201_CREATED)
    def register(payload: Registration, response: Response) -> dict:
        name = payload.name or payload.email.split("@", 1)[0]
        password_hash = password_hasher.hash(payload.password)
        token = secrets.token_urlsafe(32)
        expires_at = int(time.time()) + SESSION_MAX_AGE
        try:
            with connect(db_path) as connection:
                cursor = connection.execute(
                    "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                    (name, payload.email, password_hash),
                )
                user_id = cursor.lastrowid
                connection.execute(
                    "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                    (hashlib.sha256(token.encode("utf-8")).hexdigest(), user_id, expires_at),
                )
                user = connection.execute(
                    "SELECT id, name, email FROM users WHERE id = ?", (user_id,)
                ).fetchone()
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="Пользователь с таким email уже существует") from exc
        response.set_cookie(
            COOKIE_NAME,
            token,
            max_age=SESSION_MAX_AGE,
            httponly=True,
            secure=secure_cookie,
            samesite="strict",
            path="/",
        )
        return public_user(user)

    @app.post("/api/auth/login")
    def login(payload: Credentials, response: Response) -> dict:
        with connect(db_path) as connection:
            row = connection.execute(
                "SELECT id, name, email, password_hash FROM users WHERE email = ?",
                (payload.email,),
            ).fetchone()
        if row is None or not password_hasher.verify(payload.password, row["password_hash"]):
            raise HTTPException(status_code=401, detail="Неверный email или пароль")
        token = secrets.token_urlsafe(32)
        with connect(db_path) as connection:
            connection.execute(
                "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                (
                    hashlib.sha256(token.encode("utf-8")).hexdigest(),
                    row["id"],
                    int(time.time()) + SESSION_MAX_AGE,
                ),
            )
        response.set_cookie(
            COOKIE_NAME,
            token,
            max_age=SESSION_MAX_AGE,
            httponly=True,
            secure=secure_cookie,
            samesite="strict",
            path="/",
        )
        return public_user(row)

    @app.get("/api/auth/me")
    def me(user: authenticated_user) -> dict:
        return user

    @app.post("/api/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
    def logout(request: Request) -> Response:
        token = request.cookies.get(COOKIE_NAME)
        if token:
            token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
            with connect(db_path) as connection:
                connection.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        response.delete_cookie(COOKIE_NAME, path="/", httponly=True, secure=secure_cookie, samesite="strict")
        return response

    @app.get("/api/cart")
    def get_cart(user: authenticated_user) -> dict:
        with connect(db_path) as connection:
            rows = connection.execute(
                """SELECT products.id, products.name, products.category, products.price,
                          products.unit, products.coverage, products.description, products.image,
                          products.specs, cart_items.quantity
                   FROM cart_items JOIN products ON products.id = cart_items.product_id
                   WHERE cart_items.user_id = ? ORDER BY products.rowid""",
                (user["id"],),
            ).fetchall()
        items = [
            {"product": product_from_row(row), "quantity": row["quantity"]}
            for row in rows
        ]
        return {"items": items, "total": sum(item["product"]["price"] * item["quantity"] for item in items)}

    @app.put("/api/cart/{product_id}")
    def update_cart(product_id: str, payload: CartUpdate, user: authenticated_user) -> dict:
        with connect(db_path) as connection:
            product = connection.execute("SELECT id FROM products WHERE id = ?", (product_id,)).fetchone()
            if product is None:
                raise HTTPException(status_code=404, detail="Товар не найден")
            connection.execute(
                """INSERT INTO cart_items (user_id, product_id, quantity) VALUES (?, ?, ?)
                   ON CONFLICT (user_id, product_id) DO UPDATE SET quantity = excluded.quantity""",
                (user["id"], product_id, payload.quantity),
            )
        return {"product_id": product_id, "quantity": payload.quantity}

    @app.delete("/api/cart/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_cart_item(product_id: str, user: authenticated_user) -> Response:
        with connect(db_path) as connection:
            connection.execute(
                "DELETE FROM cart_items WHERE user_id = ? AND product_id = ?",
                (user["id"], product_id),
            )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post("/api/contact", status_code=status.HTTP_201_CREATED)
    def send_contact_message(payload: ContactMessage) -> dict:
        with connect(db_path) as connection:
            cursor = connection.execute(
                "INSERT INTO contact_messages (name, email, message) VALUES (?, ?, ?)",
                (payload.name, payload.email, payload.message),
            )
        return {"id": cursor.lastrowid, "message": "Сообщение отправлено"}

    app.mount("/", StaticFiles(directory=web_dir, check_dir=False, html=True), name="frontend")
    return app


app = create_app()

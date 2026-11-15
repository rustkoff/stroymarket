"""Учебный магазин: HTML-шаблоны, JSON-каталог и формы одного origin."""
import asyncio
import hashlib
import os
import re
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager
from typing import Annotated
from urllib.parse import urlsplit

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import FastAPI, Form, HTTPException, Request, Path as PathParameter
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.db import ROOT, cart, database, initialize, product_dict, products

PUBLIC_ORIGIN = os.getenv('PUBLIC_ORIGIN', 'http://localhost:8000').rstrip('/')
COOKIE_SECURE = os.getenv('COOKIE_SECURE', 'false').lower() == 'true'
COOKIE = 'stroy_session'
PASSWORDS = PasswordHasher()
HASH_LIMIT = asyncio.Semaphore(2)
DUMMY_HASH = PASSWORDS.hash(secrets.token_urlsafe(24))
templates = Jinja2Templates(directory=ROOT / 'site')


@asynccontextmanager
async def lifespan(app):
    initialize()
    yield


app = FastAPI(title='СтройЗапас — учебный API', version='3.0', lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=os.getenv(
    'ALLOWED_HOSTS', 'localhost,127.0.0.1,rustkoff.ru,www.rustkoff.ru').split(','))
app.mount('/images', StaticFiles(directory=ROOT / 'site/images'), name='images')
app.mount('/js', StaticFiles(directory=ROOT / 'site/js'), name='js')


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def set_cookie(response, token, seconds):
    response.set_cookie(COOKIE, token, max_age=seconds, httponly=True,
                        secure=COOKIE_SECURE, samesite='lax', path='/')


def create_session(user_id=None):
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    seconds = 7 * 86400 if user_id else 3600
    with database() as db:
        db.execute('DELETE FROM sessions WHERE expires_at<?', (int(time.time()),))
        db.execute('INSERT INTO sessions VALUES (?,?,?,?)',
                   (digest(token), user_id, csrf, int(time.time()) + seconds))
    return token, csrf, seconds


@app.middleware('http')
async def session_and_limits(request: Request, call_next):
    # Формы малы. Запросы без известной длины отклоняются до разбора multipart.
    if request.method == 'POST':
        length = request.headers.get('content-length', '')
        if not length.isdigit() or int(length) > 16384:
            return JSONResponse({'detail': 'Слишком большой запрос или не указана длина.'}, status_code=413)
    request.state.session = None
    request.state.user = None
    request.state.rotated = False
    token = request.cookies.get(COOKIE, '')
    with database() as db:
        session = db.execute('SELECT * FROM sessions WHERE token_hash=? AND expires_at>?',
                             (digest(token), int(time.time()))).fetchone() if token else None
        if session:
            request.state.session = dict(session)
            if session['user_id']:
                user = db.execute('SELECT id,name,email FROM users WHERE id=?', (session['user_id'],)).fetchone()
                request.state.user = dict(user) if user else None
    new_cookie = None
    if not session and request.method == 'GET' and (request.url.path == '/' or request.url.path.endswith('.html')):
        token, csrf, seconds = create_session()
        request.state.session = {'token_hash': digest(token), 'csrf': csrf, 'user_id': None}
        new_cookie = (token, seconds)
    response = await call_next(request)
    if new_cookie and not request.state.rotated:
        set_cookie(response, *new_cookie)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['X-Frame-Options'] = 'DENY'
    if not request.url.path.startswith(('/images/', '/js/')) and request.url.path != '/style.css':
        response.headers['Cache-Control'] = 'no-store'
    return response


def render(request, name, title, status_code=200, **context):
    return templates.TemplateResponse(request=request, name=name, status_code=status_code,
        context={'title': title, 'user': request.state.user,
                 'csrf': (request.state.session or {}).get('csrf', ''),
                 'menu_products': products(), **context})


@app.exception_handler(HTTPException)
async def http_error(request, exc):
    if request.url.path.startswith('/api/'):
        return JSONResponse({'detail': exc.detail}, status_code=exc.status_code)
    return render(request, 'error.html', f'Ошибка {exc.status_code}',
                  status_code=exc.status_code, error=exc.detail)


@app.exception_handler(RequestValidationError)
async def input_error(request, exc):
    # Не возвращаем значения полей, особенно пароль, в ответе с ошибкой.
    return await http_error(request, HTTPException(422, 'Проверьте поля формы и ограничения длины.'))


def require_user(request):
    if not request.state.user:
        raise HTTPException(401, 'Для этого действия войдите в личный кабинет.')
    return request.state.user['id']


def protect(request, csrf):
    session = request.state.session
    origin = request.headers.get('origin')
    if origin and origin != PUBLIC_ORIGIN:
        raise HTTPException(403, 'Недопустимый источник запроса.')
    if request.headers.get('sec-fetch-site') == 'cross-site':
        raise HTTPException(403, 'Недопустимый источник запроса.')
    if not session or not secrets.compare_digest(session['csrf'], csrf):
        raise HTTPException(403, 'Форма устарела. Обновите страницу и повторите действие.')


def rotate_session(request, user_id=None):
    with database() as db:
        db.execute('DELETE FROM sessions WHERE token_hash=?',
                   ((request.state.session or {}).get('token_hash', ''),))
    token, _, seconds = create_session(user_id)
    response = RedirectResponse('/account.html', status_code=303)
    set_cookie(response, token, seconds)
    request.state.rotated = True
    return response


def valid_email(email):
    value = email.strip().lower()
    if len(value) > 254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
        raise HTTPException(422, 'Введите корректный email, до 254 символов.')
    return value


@app.api_route('/health', methods=['GET', 'HEAD'], tags=['Состояние'])
def health():
    with database() as db:
        db.execute('SELECT 1 FROM products LIMIT 1').fetchone()
    return {'status': 'ok'}


@app.get('/style.css', include_in_schema=False)
def stylesheet():
    from fastapi.responses import FileResponse
    return FileResponse(ROOT / 'site/style.css', media_type='text/css')


@app.get('/api/products', tags=['Каталог'])
def list_products():
    return products()


@app.get('/api/products/{product_id}', tags=['Каталог'])
def get_product(product_id: Annotated[int, PathParameter(gt=0, le=2_147_483_647)]):
    with database() as db:
        row = db.execute('SELECT * FROM products WHERE id=?', (product_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Товар не найден.')
    return product_dict(row)


@app.post('/register', tags=['Учётная запись'])
async def register(request: Request, csrf: Annotated[str, Form()],
                   name: Annotated[str, Form(min_length=2, max_length=80)],
                   email: Annotated[str, Form(max_length=254)],
                   password: Annotated[str, Form(min_length=10, max_length=128)]):
    protect(request, csrf)
    email = valid_email(email)
    if len(name.strip()) < 2 or len(password.strip()) < 10:
        raise HTTPException(422, 'Имя: от 2 символов; пароль: от 10 непробельных символов по длине.')
    async with HASH_LIMIT:
        password_hash = await run_in_threadpool(PASSWORDS.hash, password)
    try:
        with database() as db:
            user_id = db.execute('INSERT INTO users(name,email,password_hash) VALUES (?,?,?)',
                                 (name.strip(), email, password_hash)).lastrowid
    except sqlite3.IntegrityError:
        raise HTTPException(409, 'Этот email уже зарегистрирован. Войдите в аккаунт.')
    return rotate_session(request, user_id)


@app.post('/login', tags=['Учётная запись'])
async def login(request: Request, csrf: Annotated[str, Form()],
                email: Annotated[str, Form(max_length=254)],
                password: Annotated[str, Form(min_length=1, max_length=128)]):
    protect(request, csrf)
    email = valid_email(email)
    now = int(time.time())
    # Два независимых ограничения: на IP и на email, храним только их дайджесты.
    keys = [digest('ip:' + request.client.host), digest('email:' + email)]
    with database() as db:
        db.execute('DELETE FROM login_attempts WHERE attempted_at<?', (now - 900,))
        for key in keys:
            count = db.execute('SELECT count(*) FROM login_attempts WHERE key=?', (key,)).fetchone()[0]
            limit = 100 if key == keys[0] else 10
            if count >= limit:
                raise HTTPException(429, 'Слишком много попыток. Повторите через 15 минут.')
        db.executemany('INSERT INTO login_attempts VALUES (?,?)', [(k, now) for k in keys])
        user = db.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
    try:
        async with HASH_LIMIT:
            await run_in_threadpool(PASSWORDS.verify, user['password_hash'] if user else DUMMY_HASH, password)
    except VerificationError:
        raise HTTPException(401, 'Неверный email или пароль.')
    if not user:
        raise HTTPException(401, 'Неверный email или пароль.')
    return rotate_session(request, user['id'])


@app.post('/logout', tags=['Учётная запись'])
def logout(request: Request, csrf: Annotated[str, Form()]):
    protect(request, csrf)
    require_user(request)
    return rotate_session(request)


@app.get('/api/me', tags=['Учётная запись'])
def me(request: Request):
    require_user(request)
    return request.state.user


@app.get('/api/cart', tags=['Корзина'])
def read_cart(request: Request):
    return cart(require_user(request))


@app.post('/cart/add', tags=['Корзина'])
def add_cart(request: Request, csrf: Annotated[str, Form()],
             product_id: Annotated[int, Form(gt=0, le=2_147_483_647)],
             quantity: Annotated[int, Form(ge=1, le=10000)]):
    protect(request, csrf)
    user_id = require_user(request)
    with database() as db:
        if not db.execute('SELECT id FROM products WHERE id=?', (product_id,)).fetchone():
            raise HTTPException(404, 'Товар не найден.')
        old = db.execute('SELECT quantity FROM cart_items WHERE user_id=? AND product_id=?',
                         (user_id, product_id)).fetchone()
        new_quantity = quantity + (old['quantity'] if old else 0)
        if new_quantity > 10000:
            raise HTTPException(422, 'Не более 10 000 единиц одного товара.')
        db.execute('''INSERT INTO cart_items VALUES (?,?,?) ON CONFLICT(user_id,product_id)
                      DO UPDATE SET quantity=excluded.quantity''', (user_id, product_id, new_quantity))
    return RedirectResponse('/cart.html', status_code=303)


@app.post('/cart/update', tags=['Корзина'])
def update_cart(request: Request, csrf: Annotated[str, Form()],
                product_id: Annotated[int, Form(gt=0, le=2_147_483_647)],
                quantity: Annotated[int, Form(ge=0, le=10000)]):
    protect(request, csrf)
    user_id = require_user(request)
    with database() as db:
        if quantity == 0:
            result = db.execute('DELETE FROM cart_items WHERE user_id=? AND product_id=?', (user_id, product_id))
        else:
            result = db.execute('UPDATE cart_items SET quantity=? WHERE user_id=? AND product_id=?',
                                (quantity, user_id, product_id))
        if not result.rowcount:
            raise HTTPException(404, 'Товар отсутствует в вашей корзине.')
    return RedirectResponse('/cart.html', status_code=303)


@app.post('/orders', tags=['Заказы'])
def create_order(request: Request, csrf: Annotated[str, Form()]):
    protect(request, csrf)
    user_id = require_user(request)
    with database() as db:
        # Блокировка записи до чтения корзины: повторное нажатие не дублирует заказ.
        db.execute('BEGIN IMMEDIATE')
        rows = db.execute('''SELECT p.*,c.quantity FROM cart_items c JOIN products p
                             ON p.id=c.product_id WHERE c.user_id=?''', (user_id,)).fetchall()
        if not rows:
            raise HTTPException(409, 'Нельзя оформить пустую корзину.')
        order_id = db.execute('INSERT INTO orders(user_id) VALUES (?)', (user_id,)).lastrowid
        db.executemany('INSERT INTO order_items VALUES (?,?,?,?,?,?)',
                       [(order_id, p['id'], p['name'], p['unit'], p['price'], p['quantity']) for p in rows])
        db.execute('DELETE FROM cart_items WHERE user_id=?', (user_id,))
    return RedirectResponse(f'/order.html?id={order_id}', status_code=303)


def owned_order(request, order_id):
    user_id = require_user(request)
    with database() as db:
        order = db.execute('SELECT * FROM orders WHERE id=? AND user_id=?', (order_id, user_id)).fetchone()
        if not order:
            raise HTTPException(404, 'Заказ не найден.')
        items = [dict(r) for r in db.execute('SELECT * FROM order_items WHERE order_id=?', (order_id,))]
    return {'order': dict(order), 'items': items, 'total': sum(p['price']*p['quantity'] for p in items)}


@app.get('/api/orders/{order_id}', tags=['Заказы'])
def order_data(request: Request, order_id: Annotated[int, PathParameter(gt=0, le=2_147_483_647)]):
    return owned_order(request, order_id)


@app.post('/feedback', tags=['Обратная связь'])
def feedback(request: Request, csrf: Annotated[str, Form()],
             name: Annotated[str, Form(min_length=2, max_length=80)],
             email: Annotated[str, Form(max_length=254)],
             message: Annotated[str, Form(min_length=10, max_length=2000)],
             topic: Annotated[str, Form(max_length=100)] = 'Общий вопрос'):
    protect(request, csrf)
    user_id = require_user(request)
    email = valid_email(email)
    if len(name.strip()) < 2 or len(message.strip()) < 10:
        raise HTTPException(422, 'Проверьте имя и сообщение.')
    with database() as db:
        db.execute('INSERT INTO feedback(user_id,name,email,topic,message) VALUES (?,?,?,?,?)',
                   (user_id, name.strip(), email, topic.strip(), message.strip()))
    return render(request, 'contacts.html', 'Контакты', notice='Сообщение сохранено в учебной базе. Email не отправлялся.')


@app.api_route('/', methods=['GET', 'HEAD'], include_in_schema=False)
def home(request: Request):
    return render(request, 'index.html', 'Главная', products=products()[:6])


@app.api_route('/{page}.html', methods=['GET', 'HEAD'], include_in_schema=False)
def html_page(request: Request, page: str):
    if page == 'index':
        return home(request)
    if page == 'catalog':
        return render(request, 'catalog.html', 'Каталог', products=products())
    if page == 'contacts':
        return render(request, 'contacts.html', 'Контакты')
    if page == 'cart':
        rows = cart(request.state.user['id']) if request.state.user else []
        return render(request, 'cart.html', 'Корзина', cart=rows, total=sum(p['subtotal'] for p in rows))
    if page == 'account':
        with database() as db:
            orders = [dict(r) for r in db.execute('SELECT * FROM orders WHERE user_id=? ORDER BY id DESC',
                       ((request.state.user or {}).get('id', 0),))]
        return render(request, 'account.html', 'Личный кабинет', orders=orders)
    if page == 'order':
        value = request.query_params.get('id', '')
        if not value.isascii() or not value.isdigit() or len(value)>10 or int(value)>2_147_483_647:
            raise HTTPException(422, 'Нужен номер заказа.')
        return render(request, 'order.html', 'Мой заказ', **owned_order(request, int(value)))
    with database() as db:
        row = db.execute('SELECT * FROM products WHERE slug=?', (page,)).fetchone()
    if not row:
        raise HTTPException(404, 'Страница не найдена.')
    p = product_dict(row)
    return render(request, 'product.html', p['short_name'], product=p)

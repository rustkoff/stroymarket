"""Важные серверные сценарии на отдельной временной SQLite, без рабочей БД."""
import re

import pytest
from fastapi.testclient import TestClient

from app.db import database
from app.main import app, PASSWORDS

PASSWORD = 'Study-only-83-pass'


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_PATH', str(tmp_path / 'test.sqlite3'))
    with TestClient(app, base_url='http://localhost:8000') as c:
        yield c


def token(c):
    r = c.get('/account.html')
    return re.search(r'name="csrf" value="([^"]+)"', r.text)[1]


def post(c, path, **data):
    return c.post(path, data={'csrf': token(c), **data}, follow_redirects=False)


def register(c, email='student@example.test'):
    return post(c, '/register', name='Учебный пользователь', email=email, password=PASSWORD)


def test_catalog_comes_from_db(client):
    rows = client.get('/api/products').json()
    assert len(rows) == 15
    assert client.get('/api/products/1').json()['slug'] == 'cement'
    assert client.get('/api/products/999').status_code == 404
    assert client.get('/api/products/no').status_code == 422
    with database() as db:
        db.execute('UPDATE products SET price=? WHERE id=?', (777,1))
    assert '777 ₽' in client.get('/cement.html').text
    assert 'data-price="777"' in client.get('/catalog.html').text
    assert 'data-price="777"' in client.get('/index.html').text


def test_registration_hash_session_and_logout(client):
    old_csrf = token(client)
    old_cookie = client.cookies.get('stroy_session')
    r = register(client)
    assert r.status_code == 303
    assert 'HttpOnly' in r.headers['set-cookie'] and 'SameSite=lax' in r.headers['set-cookie']
    assert client.cookies.get('stroy_session') != old_cookie
    me = client.get('/api/me').json()
    assert me['email'] == 'student@example.test' and 'password_hash' not in me
    with database() as db:
        h = db.execute('SELECT password_hash FROM users').fetchone()[0]
        assert h.startswith('$argon2id$') and PASSWORDS.verify(h,PASSWORD)
        assert PASSWORD not in h
        assert not db.execute('SELECT 1 FROM sessions WHERE token_hash=?',(old_cookie,)).fetchone()
    assert client.post('/logout', data={'csrf':old_csrf}).status_code == 403
    assert post(client,'/logout').status_code == 303
    assert client.get('/api/me').status_code == 401
    assert post(client,'/login',email='STUDENT@example.test',password=PASSWORD).status_code == 303


@pytest.mark.parametrize('data', [
    {'name':'A','email':'a@example.test','password':PASSWORD},
    {'name':'  ','email':'a@example.test','password':PASSWORD},
    {'name':'Студент','email':'broken','password':PASSWORD},
    {'name':'Студент','email':'a@example.test','password':'short'},
    {'name':'Студент','email':'a@example.test','password':' '*10},
    {'name':'Студент','email':'a@example.test','password':'x'*129},
])
def test_invalid_registration(client,data):
    assert post(client,'/register',**data).status_code == 422
    with database() as db:
        assert db.execute('SELECT count(*) FROM users').fetchone()[0] == 0


def test_duplicate_email_and_bad_login(client):
    register(client)
    assert register(client, ' STUDENT@example.test ').status_code == 409
    post(client,'/logout')
    assert post(client,'/login',email='student@example.test',password='bad').status_code == 401
    assert post(client,'/login',email='missing@example.test',password=PASSWORD).status_code == 401
    assert client.get('/api/me').status_code == 401


def test_login_rate_limit(client):
    for _ in range(10):
        assert post(client,'/login',email='missing@example.test',password=PASSWORD).status_code == 401
    assert post(client,'/login',email='missing@example.test',password=PASSWORD).status_code == 429


@pytest.mark.parametrize('path,data', [('/cart/add',{'product_id':1,'quantity':1}),
    ('/cart/update',{'product_id':1,'quantity':0}),('/orders',{}),
    ('/feedback',{'name':'Студент','email':'a@example.test','message':'Учебное сообщение'})])
def test_anonymous_actions_denied(client,path,data):
    assert post(client,path,**data).status_code == 401


def test_csrf_and_origin(client):
    register(client)
    assert client.post('/orders',data={'csrf':'bad'}).status_code == 403
    assert client.post('/orders',data={'csrf':token(client)}, headers={'Origin':'https://evil.example'}).status_code == 403
    assert client.post('/orders',data={'csrf':token(client)}, headers={'Sec-Fetch-Site':'cross-site'}).status_code == 403
    assert client.post('/register',content='a'*17000).status_code == 413


def test_cart_and_atomic_order(client):
    register(client)
    assert post(client,'/orders').status_code == 409
    assert post(client,'/cart/add',product_id=1,quantity=2).status_code == 303
    post(client,'/cart/add',product_id=1,quantity=1)
    rows=client.get('/api/cart').json()
    assert rows[0]['quantity'] == 3 and rows[0]['subtotal'] == 1470
    post(client,'/cart/update',product_id=1,quantity=4)
    post(client,'/cart/add',product_id=2,quantity=2)
    post(client,'/cart/update',product_id=2,quantity=0)
    r=post(client,'/orders'); assert r.status_code == 303
    order_id=int(r.headers['location'].split('=')[1])
    data=client.get(f'/api/orders/{order_id}').json()
    assert data['total'] == 1960 and data['items'][0]['quantity'] == 4
    assert client.get('/api/cart').json() == []
    assert post(client,'/orders').status_code == 409
    with database() as db: db.execute('UPDATE products SET price=? WHERE id=?',(999,1))
    assert client.get(f'/api/orders/{order_id}').json()['total'] == 1960
    post(client,'/logout'); register(client,'second@example.test')
    assert client.get(f'/api/orders/{order_id}').status_code == 404
    assert client.get(f'/order.html?id={order_id}').status_code == 404
    assert client.get('/api/cart').json() == []
    assert post(client,'/cart/update',product_id=1,quantity=5).status_code == 404


@pytest.mark.parametrize('pid,quantity,status',[(1,0,422),(1,-1,422),(1,10001,422),(999,1,404),(1,'1.5',422),(1,"1; DROP TABLE users",422)])
def test_invalid_cart(client,pid,quantity,status):
    register(client)
    assert post(client,'/cart/add',product_id=pid,quantity=quantity).status_code == status
    assert client.get('/api/cart').json() == []


def test_sql_and_html_injection(client):
    name='<script>alert(1)</script>'
    r=post(client,'/register',name=name,email="o'reilly@example.test",password=PASSWORD)
    assert r.status_code == 303
    assert '&lt;script&gt;' in client.get('/account.html').text
    assert '<script>alert(1)' not in client.get('/account.html').text
    post(client,'/logout')
    assert post(client,'/login',email="'OR'1'='1@example.test",password=PASSWORD).status_code == 401


def test_feedback_saved_and_validated(client):
    register(client)
    assert post(client,'/feedback',name='Студент',email='a@example.test',message='short').status_code == 422
    r=post(client,'/feedback',name='Студент',email='a@example.test',message='Учебное сообщение для проверки')
    assert r.status_code == 200 and 'Email не отправлялся' in r.text
    with database() as db:
        assert db.execute('SELECT count(*) FROM feedback').fetchone()[0] == 1


def test_expired_session(client):
    register(client)
    with database() as db: db.execute('UPDATE sessions SET expires_at=?',(0,))
    assert client.get('/api/me').status_code == 401


def test_no_database_or_templates_exposed(client):
    for path in ['/var/shop.sqlite3','/app/products.json','/base.html','/product.html','/.env']:
        assert client.get(path).status_code == 404


@pytest.mark.parametrize('path', [
    '/api/products/999999999999999999999999999',
    '/api/orders/999999999999999999999999999',
    '/order.html?id=999999999999999999999999999',
    '/order.html?id=%C2%B2',
])
def test_extreme_identifiers_rejected(client,path):
    register(client)
    assert client.get(path).status_code == 422

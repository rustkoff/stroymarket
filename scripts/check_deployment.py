"""Проверки HTTPS и сохранения данных при restart/recreate собственного контейнера."""
import hashlib
import json
import re
import secrets
import socket
import ssl
import sqlite3
import subprocess
import time
from pathlib import Path

import httpx

BASE='https://rustkoff.ru'
OUT=Path('docs/report-assets/pr4'); OUT.mkdir(parents=True,exist_ok=True)
result={'base':BASE,'checks':[]}
users=[]

def check(value, text):
    assert value,text
    result['checks'].append(text)


def token(c):
    r=c.get('/account.html')
    return re.search(r'name="csrf" value="([^"]+)"',r.text)[1]


def post(c,path,**data):
    return c.post(path,data={'csrf':token(c),**data})


def account(c):
    email=f'deploy-{secrets.token_hex(8)}@example.test';password=secrets.token_urlsafe(20)
    check(post(c,'/register',name='Проверка публикации',email=email,password=password).status_code==303,'HTTPS: регистрация')
    uid=c.get('/api/me').json()['id']; users.append(uid)
    return uid,email,password


def ready():
    for _ in range(40):
        try:
            if httpx.get(BASE+'/health',timeout=3).status_code==200:return
        except httpx.HTTPError:pass
        time.sleep(.5)
    raise AssertionError('Контейнер не готов после изменения состояния')


ready()
with httpx.Client(base_url=BASE,timeout=20,follow_redirects=False) as c:
    check(httpx.get('http://rustkoff.ru/catalog.html',follow_redirects=False).headers.get('location')==BASE+'/catalog.html','HTTP → HTTPS 301 с сохранением пути')
    check(c.head('/').status_code==200,'HEAD главной: HTTP 200')
    check(c.get('/health').status_code==200,'HTTPS health: HTTP 200')
    check(c.get('/api/me').status_code==401,'HTTPS: профиль закрыт без входа')
    uid,email,password=account(c)
    for path in ['/api/products/999999999999999999999999999',
                 '/api/orders/999999999999999999999999999',
                 '/order.html?id=999999999999999999999999999',
                 '/order.html?id=%C2%B2']:
        check(c.get(path).status_code==422,'HTTPS: некорректный идентификатор отклонён: '+path)
    cookie=c.cookies.get('stroy_session')
    check(post(c,'/register',name=' ',email='invalid',password='short').status_code==422,'HTTPS: неверная регистрация отклонена')
    check(post(c,'/register',name='Дубликат',email=email,password=password).status_code==409,'HTTPS: повторный email отклонён')
    check(post(c,'/cart/add',product_id=1,quantity=-1).status_code==422,'HTTPS: неверное количество отклонено')
    check(c.post('/orders',data={'csrf':'bad'}).status_code==403,'HTTPS: неверный CSRF отклонён')
    check(c.post('/orders',data={'csrf':token(c)},headers={'Origin':'https://invalid.example'}).status_code==403,'HTTPS: чужой Origin отклонён')
    post(c,'/cart/add',product_id=1,quantity=4)
    order_id=int(post(c,'/orders').headers['location'].split('=')[1])
    post(c,'/cart/add',product_id=2,quantity=2)
    before=c.get('/api/cart').json()
    for command,name in [(['docker-compose','restart','shop'],'restart'),(['docker-compose','up','-d','--force-recreate','shop'],'recreate')]:
        proc=subprocess.run(command,capture_output=True,text=True,check=True)
        ready()
        check(c.get('/api/cart').json()==before,f'{name}: корзина сохранена')
        check(c.get(f'/api/orders/{order_id}').json()['total']==1960,f'{name}: заказ сохранён')
        check(c.get('/api/me').json()['id']==uid,f'{name}: сессия сохранена')
    with httpx.Client(base_url=BASE,timeout=20) as other:
        account(other)
        check(other.get(f'/api/orders/{order_id}').status_code==404,'HTTPS: чужой заказ недоступен')
        check(other.get('/api/cart').json()==[],'HTTPS: корзины разных пользователей разделены')
    check(post(c,'/logout').status_code==303,'HTTPS: выход')
    check(c.get('/api/me').status_code==401,'HTTPS: сессия закрыта после выхода')
    check(post(c,'/login',email=email,password='wrong').status_code==401,'HTTPS: неправильный пароль отклонён')
    response=post(c,'/login',email=email,password=password)
    check(response.status_code==303,'HTTPS: правильный пароль принят')
    cookie_header=response.headers['set-cookie']
    check(all(x in cookie_header for x in ['Secure','HttpOnly','SameSite=lax']),'HTTPS: Secure, HttpOnly, SameSite=lax')
    db=sqlite3.connect('/var/lib/stroymarket/shop.sqlite3')
    row=db.execute('SELECT id,password_hash FROM users WHERE id=?',(uid,)).fetchone()
    check(row[1].startswith('$argon2id$') and password not in row[1],'Рабочая SQLite: хранится Argon2id, открытого пароля нет')
    result['hash_example']={'id':row[0],'email':'учебная запись (удалена после проверки)','password_hash':row[1]}
    db.close()

ctx=ssl.create_default_context()
with socket.create_connection(('rustkoff.ru',443),timeout=10) as sock:
    with ctx.wrap_socket(sock,server_hostname='rustkoff.ru') as tls:
        cert=tls.getpeercert()
        result['tls']={'version':tls.version(),'cipher':tls.cipher()[0],
                       'notBefore':cert['notBefore'],'notAfter':cert['notAfter'],
                       'subjectAltName':cert['subjectAltName'],
                       'issuer':cert['issuer'],'verified':True}
check(result['tls']['verified'],'Сертификат проверен системным CA-хранилищем, имя хоста совпадает')
# Адресная очистка только двух записей, созданных этим запуском.
db=sqlite3.connect('/var/lib/stroymarket/shop.sqlite3');db.execute('PRAGMA foreign_keys=ON')
with db:
    for uid in users:
        db.execute('DELETE FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE user_id=?)',(uid,))
        for statement in ['DELETE FROM orders WHERE user_id=?',
                          'DELETE FROM cart_items WHERE user_id=?',
                          'DELETE FROM feedback WHERE user_id=?',
                          'DELETE FROM sessions WHERE user_id=?']:
            db.execute(statement,(uid,))
        db.execute('DELETE FROM users WHERE id=?',(uid,))
db.close()
result['temporary_accounts_removed']=len(users)
result['timestamp_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
(OUT/'deployment-checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(f"Deployment: {len(result['checks'])} checks passed; TLS {result['tls']['version']}; temporary accounts removed")

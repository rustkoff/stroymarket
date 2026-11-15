"""Иллюстрации ПР 3–4 из фактических результатов; без секретов и VPN-конфигураций."""
import html
import json
import subprocess
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parent.parent
PR3=ROOT/'docs/report-assets/pr3';PR4=ROOT/'docs/report-assets/pr4'
style='''<style>body{margin:0;padding:30px;background:#fff;color:#202a23;font:20px Arial}h1{font-size:30px;color:#305b46}h2{font-size:23px}pre{font:17px Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f6f3;padding:22px;border:1px solid #b9c9bc}table{border-collapse:collapse;width:100%;font-size:19px}td,th{padding:16px;border:1px solid #b9c9bc;text-align:left;overflow-wrap:anywhere}.note{color:#51665b}.box{padding:18px;background:#eef4ef;border:2px solid #305b46;border-radius:8px}svg text{font:18px Arial;fill:#202a23}</style>'''

def frame(title,body):return '<!doctype html><html lang="ru"><meta charset="utf-8">'+style+'<h1>'+title+'</h1>'+body+'</html>'

schema='''<svg viewBox="0 0 1080 620" width="1080" height="620" aria-label="Связи таблиц SQLite"><defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#305b46"/></marker></defs>
<g fill="#eef4ef" stroke="#305b46" stroke-width="2"><rect x="20" y="50" width="270" height="150" rx="8"/><rect x="410" y="50" width="270" height="150" rx="8"/><rect x="790" y="50" width="270" height="150" rx="8"/><rect x="20" y="300" width="270" height="140" rx="8"/><rect x="410" y="300" width="270" height="140" rx="8"/><rect x="790" y="300" width="270" height="140" rx="8"/><rect x="20" y="510" width="660" height="85" rx="8"/></g>
<g><text x="40" y="85">users</text><text x="40" y="120">PK id · email UNIQUE</text><text x="40" y="150">name · password_hash</text><text x="40" y="180">created_at</text>
<text x="430" y="85">cart_items</text><text x="430" y="120">PK/FK user_id, product_id</text><text x="430" y="150">quantity 1…10000</text>
<text x="810" y="85">products (15 записей)</text><text x="810" y="120">PK id · slug UNIQUE</text><text x="810" y="150">name · price · unit</text><text x="810" y="180">image · specs · source</text>
<text x="40" y="335">orders</text><text x="40" y="370">PK id · FK user_id</text><text x="40" y="400">created_at · status</text>
<text x="430" y="335">order_items</text><text x="430" y="370">PK/FK order_id, product_id</text><text x="430" y="400">name · unit · price · quantity</text>
<text x="810" y="335">sessions</text><text x="810" y="370">PK token_hash · FK user_id</text><text x="810" y="400">csrf · expires_at</text>
<text x="40" y="545">feedback: PK id · FK user_id · name · email · topic · message</text><text x="40" y="578">login_attempts: key (дайджест) · attempted_at</text></g>
<g stroke="#305b46" stroke-width="2" fill="none" marker-end="url(#arrow)"><path d="M290 120 H410"/><path d="M680 120 H790"/><path d="M155 200 V300"/><path d="M290 370 H410"/><path d="M680 330 H740 V180 H790"/><path d="M290 170 H350 V480 H925 V440"/><path d="M20 170 H5 V550 H20"/></g>
<text x="320" y="100">1 : N</text><text x="705" y="100">N : 1</text><text x="168" y="255">1 : N</text><text x="320" y="350">1 : N</text></svg>'''
(PR3/'database-schema.html').write_text(frame('СтройЗапас — структура SQLite',schema+'<p class="note">Стрелки показывают связи PK/FK. Заказ хранит снимок названия, цены и количества. Сессии и сообщения связаны с пользователем.</p>'))
checks=json.loads((PR4/'deployment-checks.json').read_text());sample=checks['hash_example']
body='<p>Результат SELECT id, password_hash FROM users для временной учебной записи.</p><table><tr><th>id</th><th>password_hash</th></tr><tr><td>'+str(sample['id'])+'</td><td>'+html.escape(sample['password_hash'])+'</td></tr></table><p class="note">Алгоритм Argon2id; в поле нет открытого пароля. Запись удалена после проверки. Email, cookie и пароль на снимке отсутствуют.</p>'
(PR3/'password-hash.html').write_text(frame('Хранение пароля в SQLite',body))
log=(ROOT/'tmp/docker-build-final.log').read_text()
lines=log.splitlines(); selected=lines[:20]+lines[-18:]
for _ in range(60):
    health=subprocess.check_output(['docker','inspect','--format','{{.State.Health.Status}}','stroymarket-shop-1'],text=True).strip()
    if health=='healthy':break
    time.sleep(.5)
assert health=='healthy'
ps=subprocess.check_output(['docker-compose','ps'],cwd=ROOT,text=True)
ps='\n'.join(line.rstrip() for line in ps.splitlines())+'\n'
body='<p>Фактический вывод сборки и состояния контейнера (15.11.2026).</p><pre>'+html.escape('\n'.join(selected))+'</pre><pre>'+html.escape(ps)+'</pre>'
(PR4/'container.html').write_text(frame('Docker: сборка и запуск СтройЗапас',body))
tls=checks['tls'];server=json.loads((PR4/'server-checks.json').read_text())
body='<p class="box">Проверяемый адрес: <strong>https://rustkoff.ru/</strong><br>GET /health → 200; HTTP → HTTPS → 301</p><pre>'+html.escape(json.dumps(tls,ensure_ascii=False,indent=2))+'</pre><p>Проверка выполнена с VDS через публичное доменное имя с системным CA-хранилищем. Не используется отключение проверки сертификата.</p><p class="note">Это сохранённый результат проверки TLS, а не имитация адресной строки браузера.</p>'
(PR4/'https-verification.html').write_text(frame('HTTPS и сертификат опубликованного приложения',body))
body='<p>Дата: 15.11.2026. Зафиксированные результаты до и после публикации.</p><table><tr><th>Проверка</th><th>До</th><th>После</th></tr><tr><td>HTTPS /</td><td>200, заглушка</td><td>200, СтройЗапас</td></tr><tr><td>HTTP :80</td><td>Не слушается</td><td>301 + ACME webroot</td></tr><tr><td>Nginx / Xray / AdGuard / SSH</td><td>active</td><td>active, прежние PID</td></tr><tr><td>Firewall / SNI stream</td><td>Снимок сохранён</td><td>Правила неизменны</td></tr><tr><td>DoH /dns-query</td><td>404</td><td>404</td></tr><tr><td>VPN/DoH реальный клиент</td><td>Не проверялся</td><td>Требуется владелец</td></tr></table>'
(PR4/'services.html').write_text(frame('Сохранность действующих сервисов',body))
with sync_playwright() as pw:
 browser=pw.chromium.launch(args=['--no-sandbox'])
 page=browser.new_page(viewport={'width':1160,'height':900})
 for file in [PR3/'database-schema.html',PR3/'password-hash.html',PR4/'container.html',PR4/'https-verification.html',PR4/'services.html']:
  page.goto(file.as_uri());page.locator('body').screenshot(path=str(file.with_suffix('.png')))
 page.goto('https://rustkoff.ru/account.html');page.screenshot(path=str(PR3/'registration-login.png'))
 page.goto('https://rustkoff.ru/');page.wait_for_function("Array.from(document.images).filter(i=>i.getBoundingClientRect().top<innerHeight).every(i=>i.complete&&i.naturalWidth>0)");page.screenshot(path=str(PR4/'published-home.png'))
 page.set_viewport_size({'width':360,'height':850})
 for slug in ['index','catalog','cement','cart','contacts','account']:
  page.goto(f'https://rustkoff.ru/{slug}.html');page.screenshot(path=str(PR3/(slug+'-mobile-overview.png')))
 browser.close()
print('Report figures created')

"""Playwright: опубликованный UI, ПР 2, ссылки и 360 px. Только учебная запись."""
import json
import os
import secrets
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from playwright.sync_api import sync_playwright

BASE = os.environ.get('CHECK_URL', 'http://localhost:8000')
OUT = Path(os.environ.get('CHECK_OUTPUT', 'tmp/browser-local'))
OUT.mkdir(parents=True, exist_ok=True)
results = {'base': BASE, 'checks': [], 'javascript_errors': [], 'http_errors': []}


def check(value, description):
    assert value, description
    results['checks'].append(description)


with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, args=['--no-sandbox'])
    results['browser'] = browser.version
    context = browser.new_context(viewport={'width':1280,'height':900})
    page = context.new_page()
    page.on('pageerror', lambda e: results['javascript_errors'].append(str(e)))
    page.on('response', lambda r: results['http_errors'].append({'url':r.url,'status':r.status})
            if r.url.startswith(BASE) and r.status >= 400 else None)
    page.goto(BASE + '/catalog.html')
    page.wait_for_function("!document.querySelector('#currency-status').getAttribute('aria-busy') || document.querySelector('#currency-status').getAttribute('aria-busy')==='false'")
    results['currency_real_status'] = page.locator('#currency-status').inner_text()
    check(page.locator('.product-card').count()==15,'Каталог содержит 15 товаров из базы')
    page.locator('#search').fill(' KNAUF ')
    check(page.locator('.product-card:visible').count()==2,'Поиск KNAUF: 2 товара')
    page.locator('#category').select_option(label='Изоляция')
    check(page.locator('.product-card:visible').count()==1,'Совместный фильтр: 1 товар')
    page.get_by_role('button',name='Сбросить',exact=True).click()
    page.locator('#sort').select_option('price-desc')
    prices=page.locator('.product-card:visible').evaluate_all('(cards)=>cards.map(c=>Number(c.dataset.price))')
    check(prices==sorted(prices,reverse=True),'Сортировка цены по убыванию')
    page.get_by_role('button',name='Сбросить',exact=True).click()
    page.locator('#material').select_option('drywall');page.locator('#amount').fill('9');page.locator('#reserve').fill('10')
    page.locator('#calculator-form button').click()
    check('листов: 4' in page.locator('#calculator-result').inner_text(),'Площадь 9 м² и запас 10%: 4 листа')
    page.screenshot(path=str(OUT/'catalog-calculator.png'),full_page=False)
    for slug,amount,reserve,expected in [('drywall-knauf','2,7','0','листов: 3'),('board','0,09','0','штук: 2'),('brick','0,0039','0','штук: 2'),('block','0,046875','0','штук: 2'),('insulation','9','0','упаковок: 1'),('plywood','2,325625','0','листов: 1'),('drywall-wind','3,6','0','листов: 1'),('drywall-multicomfort','3','0','листов: 1')]:
        page.locator('#material').select_option(slug);page.locator('#amount').fill(amount);page.locator('#reserve').fill(reserve);page.locator('#calculator-form button').click()
        check(expected in page.locator('#calculator-result').inner_text(),f'Расчёт {slug}: {expected}')
    page.locator('#amount').fill('0');page.locator('#calculator-form button').click()
    check(page.locator('#amount').get_attribute('aria-invalid')=='true','Неверная площадь отклонена')
    check(page.locator('#amount').evaluate('(e)=>e===document.activeElement'),'Фокус калькулятора на ошибочном поле')
    page.locator('#currency-status').scroll_into_view_if_needed()
    page.screenshot(path=str(OUT/'currency-real.png'))
    # Настоящее отключение сети, когда HTML уже загружен.
    context.set_offline(True)
    page.wait_for_function("!document.querySelector('#currency-reload').disabled")
    page.locator('#currency-reload').click()
    page.wait_for_function("document.querySelector('#currency-status').textContent.includes('Не удалось')")
    check('Не удалось' in page.locator('#currency-status').inner_text(),'Offline API: понятная ошибка')
    page.locator('#search').fill('цемент')
    check(page.locator('.product-card:visible').count()==1,'Фильтр работает при Offline')
    page.screenshot(path=str(OUT/'currency-offline.png'))
    context.set_offline(False)
    page.wait_for_function("!document.querySelector('#currency-reload').disabled")
    page.locator('#currency-reload').click()
    page.wait_for_function("document.querySelector('#currency-status').getAttribute('aria-busy')==='false'")
    results['currency_recovery_status']=page.locator('#currency-status').inner_text()
    # Регистрация через настоящий интерфейс. Секреты не записываются в результаты.
    page.goto(BASE+'/account.html')
    page.locator('#register-name').fill('Учебная проверка')
    email=f'check-{secrets.token_hex(6)}@example.test';password=secrets.token_urlsafe(18)
    page.locator('#register-email').fill(email);page.locator('#register-password').fill(password)
    page.get_by_role('button',name='Зарегистрироваться',exact=True).click()
    page.wait_for_url('**/account.html')
    check(page.get_by_role('heading',name='Профиль').count()==1,'Регистрация открывает профиль')
    page.goto(BASE+'/cement.html')
    page.locator('#quantity').fill('4');page.get_by_role('button',name='Добавить в корзину').click()
    check('1960 ₽' in page.locator('main').inner_text(),'Корзина 4 × 490 = 1960 ₽')
    page.screenshot(path=str(OUT/'cart-desktop.png'))
    page.reload();check('1960 ₽' in page.locator('main').inner_text(),'Корзина сохраняется при перезагрузке страницы')
    page.get_by_role('button',name='Оформить учебный заказ').click()
    check(page.url.split('?')[0].endswith('/order.html'),'Заказ открывается после оформления')
    check('1960 ₽' in page.locator('main').inner_text(),'Сумма заказа совпадает')
    page.screenshot(path=str(OUT/'order.png'))
    page.goto(BASE+'/contacts.html');page.locator('#feedback-form button').click()
    check(page.locator('[aria-invalid=true]').count()==3,'Ошибки трёх полей обратной связи')
    page.screenshot(path=str(OUT/'feedback-errors.png'))
    page.locator('#name').fill('Учебная проверка');page.locator('#email').fill(email);page.locator('#message').fill('Проверка сохранения учебного сообщения.')
    page.locator('#feedback-form button').click()
    check('Email не отправлялся' in page.locator('main').inner_text(),'Сообщение сохранено без заявления об email')
    page.screenshot(path=str(OUT/'feedback-saved.png'))
    # Внутренние ссылки и все типы страниц, включая новые товары.
    rows=context.request.get(BASE+'/api/products').json()
    urls=['/','/catalog.html','/contacts.html','/cart.html','/account.html']+[f"/{p['slug']}.html" for p in rows]
    links=set()
    page.set_viewport_size({'width':360,'height':800})
    for url in urls:
        response=page.goto(BASE+url)
        check(response.status==200,f'HTML {url}: HTTP 200')
        check(page.evaluate('document.documentElement.scrollWidth<=innerWidth'),f'360 px без переполнения: {url}')
        check(page.locator('h1').count()==1,f'Единственный h1: {url}')
        for value in page.locator('a[href],img[src],script[src],link[href]').evaluate_all('(els)=>els.map(e=>e.getAttribute("href")||e.getAttribute("src"))'):
            full=urljoin(page.url,value)
            if urlsplit(full).netloc==urlsplit(BASE).netloc: links.add(full.split('#')[0])
        if url in ['/','/catalog.html','/contacts.html','/cart.html','/cement.html','/account.html']:
            page.screenshot(path=str(OUT/((url.strip('/').replace('.html','') or 'index')+'-mobile.png')),full_page=True)
    for link in sorted(links):
        r=context.request.get(link)
        check(r.status==200,f'Локальная ссылка/ресурс: {urlsplit(link).path}')
    page.goto(BASE+'/catalog.html');page.keyboard.press('Tab')
    check(page.locator('.skip-link').evaluate('(e)=>e===document.activeElement'),'Tab открывает ссылку к содержимому')
    page.locator('summary').focus();page.keyboard.press('Enter')
    check(page.locator('details').get_attribute('open') is not None,'Клавиатура раскрывает меню товаров')
    page.goto(BASE+'/contacts.html');page.locator('#name').focus()
    for expected in ['email','topic','message']:
        page.keyboard.press('Tab');check(page.evaluate('document.activeElement.id')==expected,f'Tab: {expected}')
    page.goto(BASE+'/docs');page.wait_for_selector('.swagger-ui .opblock',timeout=30000)
    page.set_viewport_size({'width':1280,'height':1000});page.screenshot(path=str(OUT/'api-docs.png'),full_page=False)
    page.goto(BASE+'/account.html');page.get_by_role('button',name='Выйти',exact=True).click()
    check(context.request.get(BASE+'/api/me').status==401,'Выход закрывает профиль')
    page.locator('#login-email').fill(email);page.locator('#login-password').fill(password)
    page.get_by_role('button',name='Войти',exact=True).click()
    check(page.get_by_role('heading',name='Мои заказы').count()==1,'Повторный вход, заказ сохранён')
    # Только ID созданной записи для последующей адресной очистки на сервере.
    results['temporary_user_id']=context.request.get(BASE+'/api/me').json()['id']
    check(not results['javascript_errors'],'Необработанных ошибок JavaScript нет')
    check(not results['http_errors'],'Ошибок HTTP локальных ресурсов нет')
    results['timestamp_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
    (OUT/'checks.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
    browser.close()
print(json.dumps({'assertions':len(results['checks']),'currency':results['currency_real_status'],'output':str(OUT)},ensure_ascii=False))

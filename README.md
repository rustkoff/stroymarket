# СтройЗапас — магазин стройматериалов

Учебный проект по дисциплине «Введение в интернет-технологии».
Шустов Фёдор Александрович, группа ЗН251. Тема №14 — магазин стройматериалов, калькулятор количества по площади или объёму.

**Адрес: https://rustkoff.ru/**. Выполнены ПР 1–4. HTML/CSS/JavaScript без сборки и frontend-фреймворков; Python, FastAPI, Jinja2, SQLite, Docker и существующий Nginx на VDS.

Каталог содержит 15 материалов, отдельные страницы и источники характеристик. Работают поиск, совместные фильтры, сортировка, калькулятор девяти материалов и справочный пересчёт цены в USD/EUR. Пользователь регистрируется, входит, меняет корзину и оформляет учебный заказ. Сообщения обратной связи вошедших пользователей сохраняются в SQLite. Оплаты, доставки и отправки email нет; цены и контакты учебные.

## Локальный запуск

Нужен Python 3.13. Команды из корня репозитория:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Открыть http://localhost:8000. `Ctrl+C` останавливает сервер. Таблицы и каталог создаются автоматически, учётные записи отсутствуют. Рабочая локальная БД — `var/shop.sqlite3`, она игнорируется Git. В Windows используйте `.venv\Scripts\python.exe` и `python -m uvicorn`.

Создайте собственную учебную запись на `/account.html`, используя отдельный пароль от 10 до 128 символов. Это тестовая учётная запись для проверки по методичке.

Сайт теперь требует FastAPI: `python -m http.server --directory site` не обрабатывает Jinja-шаблоны и формы. ПР 1–2 сохранены как предыдущие этапы в отчёте и истории Git (`c1e1e9b`).

## Настройки

Приложение читает переменные окружения; `.env` автоматически читает Compose. Для локального Uvicorn достаточно значений по умолчанию либо обычного `export`.

| Переменная | По умолчанию / назначение |
| --- | --- |
| `DATABASE_PATH` | `var/shop.sqlite3`; внутри контейнера `/data/shop.sqlite3` |
| `PUBLIC_ORIGIN` | `http://localhost:8000`; на VDS `https://rustkoff.ru`, без завершающего `/` |
| `COOKIE_SECURE` | `false` для локального HTTP; на VDS обязательно `true` |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1,rustkoff.ru,www.rustkoff.ru` |
| `IMAGE_TAG` | `latest`; можно выбрать сохранённую версию образа для отката |

Пример без секретов — `.env.example`. На VDS `.env` имеет права 600. Секрет подписи не нужен: cookie содержит случайный непрозрачный токен, его SHA-256 хранится в БД. Пароли и токены не записываются в исходники, образ или логи приложения.

## Docker на обычной машине

Dockerfile закрепляет Python-образ по digest и все зависимости, копирует только приложение, шаблоны и изображения. Процесс работает как UID/GID 10001. Сборка из свежего контекста не требует существующей базы.

```bash
docker build -t stroymarket:local .
docker run -d --name stroymarket-local \
  -p 127.0.0.1:8000:8000 \
  -v stroymarket-local-data:/data \
  -e PUBLIC_ORIGIN=http://localhost:8000 \
  -e COOKIE_SECURE=false stroymarket:local
```

Открыть http://localhost:8000. Именованный том сохраняется при пересоздании контейнера. Не удаляйте том, если нужны аккаунты и заказы. Healthcheck проверяет HTTP и доступность SQLite. Этот пример рассчитан на обычную сеть Docker; на действующем VDS используйте Compose ниже.

## Docker на этом VDS

Установлены Debian-пакеты Docker/Compose. Docker запущен без моста, управления iptables, IP forwarding и masquerading: `/etc/docker/daemon.json`. Пример этой настройки — `deploy/docker-daemon.example.json`. Это настройка специально для данного сервера, где уже работают VPN и firewall. Общие правила firewall и сетевые sysctl не изменены.

```bash
cd /root/stroymarket
cp .env.example .env
# Только при первоначальной настройке: PUBLIC_ORIGIN=https://rustkoff.ru,
# COOKIE_SECURE=true, ALLOWED_HOSTS=rustkoff.ru,www.rustkoff.ru,127.0.0.1
chmod 600 .env
install -d -o 10001 -g 10001 -m 700 /var/lib/stroymarket
docker-compose build
docker-compose up -d
docker-compose ps
curl --fail https://rustkoff.ru/health
```

**Не копируйте `.env.example` поверх уже настроенного `.env` при обновлении.** Compose использует сеть хоста; Uvicorn явно привязан к `127.0.0.1:18080`. У контейнера нет capabilities, включены `no-new-privileges`, read-only rootfs, ограничения памяти/CPU/PID, временный `/tmp` и ротация логов. Постоянен только `/var/lib/stroymarket:/data`. `restart: unless-stopped` и включённый `docker.service` обеспечивают запуск после перезагрузки; реальная перезагрузка VDS не проводилась. Healthcheck сообщает состояние, но сам по себе не перезапускает зависший процесс; выход процесса обрабатывает restart policy.

Сеть хоста не изолирует контейнер от других loopback-сервисов. Выбор сделан для сохранения сетевой схемы и firewall VDS; контейнер запускается без root и не получает конфигурации или сокет Docker.

## Публикация и TLS

Существующий путь обычного HTTPS: Nginx stream :443 → Xray/Reality → Nginx `127.0.0.1:8443` → FastAPI `127.0.0.1:18080`. SNI-маршрутизация, XHTTP, 3x-ui и AdGuard не редактировались. Заменён только обработчик заглушки. `www` для обычного сайта перенаправляется на основной домен.

Фрагменты конфигурации — `deploy/nginx-shop-location.conf` и `deploy/nginx-http.conf`. На сервере они подключены из `/etc/nginx/nginx.conf`. Порт 80 отдаёт ACME challenge из `/var/www/letsencrypt` и перенаправляет остальные запросы на HTTPS. Используется прежний сертификат Let's Encrypt для rustkoff.ru и www.rustkoff.ru. Certbot переведён со standalone на webroot через успешный `certbot reconfigure`; включён прежний таймер, добавлен deploy hook с проверкой и reload Nginx. Тестовое продление состоялось, текущий сертификат не заменялся тестовым. Выполненная команда: `certbot reconfigure --cert-name rustkoff.ru --webroot --webroot-path /var/www/letsencrypt --non-interactive`. Пример deploy hook — `deploy/certbot-reload.sh`.

На исходном сервере `/dns-query` возвращал 404; AdGuard TLS/DoH был отключён, внутренний HTTP DoH также возвращал 404. Это состояние сохранено. Работающий процесс AdGuard не является доказательством клиентского DoH. Полноценное VPN-подключение и DoH с реального клиента требуют отдельной проверки владельцем.

## Обновление и откат

Перед обновлением:

```bash
cd /root/stroymarket
git status --short
python3 scripts/backup.py --database /var/lib/stroymarket/shop.sqlite3 \
  --output /root/backups/stroymarket-before-update.sqlite3
docker tag stroymarket:latest stroymarket:previous
```

Продолжайте только разобрав собственные незакоммиченные изменения. Копия не перезаписывается: для следующего запуска выберите новое имя.

```bash
git pull --ff-only origin main
docker-compose build
docker-compose up -d
curl --fail https://rustkoff.ru/health
docker-compose ps
docker-compose logs --tail=50 shop
```

Откат приложения к заранее сохранённому образу, без изменения БД:

```bash
IMAGE_TAG=previous docker-compose up -d --no-build
```

Перед несовместимой миграцией БД нужен отдельный план; нынешняя инициализация только создаёт отсутствующие таблицы и добавляет отсутствующие товары, не заменяя имеющиеся записи. Для полного возврата к заглушке подготовлен `/root/backups/stroymarket-20261115/rollback.sh` (700): проверяет и возвращает прежний nginx.conf, делает reload, возвращает старую настройку Certbot и останавливает только контейнер магазина. База сохраняется. Это аварийный откат к состоянию до публикации, а не обычная команда обновления.

## Постоянные данные и резервная копия

Рабочая база: `/var/lib/stroymarket/shop.sqlite3`, рядом могут быть `-wal` и `-shm`. Каталог 700, владелец UID 10001. Не копируйте единственный файл работающей БД через `cp`: используйте SQLite backup API.

```bash
python3 scripts/backup.py --database /var/lib/stroymarket/shop.sqlite3 \
  --output /root/backups/stroymarket-20261115/manual-copy.sqlite3
```

Скрипт создаёт согласованную копию, проверяет `PRAGMA integrity_check`, задаёт 600 и отказывается перезаписывать существующий файл. Резервные копии содержат персональные данные и хеши — хранятся вне Git. Для восстановления остановите **только магазин**, сохраните текущие файлы базы отдельно, восстановите копию как `shop.sqlite3`, выставьте владельца 10001:10001 и права 600. Старые WAL/SHM от другой версии базы нельзя оставлять рядом с восстановленным файлом. Затем запустите магазин и проверьте `/health`, аккаунт и заказ. Автоматическое расписание бэкапов не настраивалось.

## Структура базы

SQLite, `foreign_keys=ON` на каждом соединении, WAL, транзакции и ожидание блокировки до 10 секунд. Схема — `app/schema.sql`, начальные товары — `app/products.json`. Денежные значения — целые рубли, количество — целые единицы продажи.

| Таблица | Поля и связи |
| --- | --- |
| `users` | `id INTEGER PK`, `name TEXT`, `email TEXT UNIQUE`, `password_hash TEXT`, `created_at TEXT` |
| `products` | `id INTEGER PK`, `slug TEXT UNIQUE`, `name`, `short_name`, `category`, `unit`, `image`, `description`, `specs` (JSON), `source`, `image_note` — TEXT; `price INTEGER > 0` |
| `cart_items` | составной PK `(user_id,product_id)`, FK на users/products; `quantity INTEGER 1…10000` |
| `orders` | `id INTEGER PK`, `user_id INTEGER FK users`, `created_at TEXT` (UTC), `status TEXT` |
| `order_items` | PK `(order_id,product_id)`, FK orders/products; `name TEXT`, `unit TEXT`, `price INTEGER`, `quantity INTEGER` — снимок покупки |
| `sessions` | `token_hash TEXT PK`, `user_id INTEGER NULL FK users`, `csrf TEXT`, `expires_at INTEGER` (Unix seconds) |
| `feedback` | `id INTEGER PK`, `user_id INTEGER FK users`, `name`, `email`, `topic`, `message`, `created_at` — TEXT |
| `login_attempts` | `key TEXT` (дайджест IP/email), `attempted_at INTEGER`; только последние 15 минут |

Основные связи: users → cart_items → products; users → orders → order_items → products. В заказ копируются имя, единица, цена и количество: изменение каталога не меняет уже оформленный заказ. Оформление в одной `BEGIN IMMEDIATE` транзакции переносит корзину в заказ и очищает её, повторное нажатие получает ошибку пустой корзины.

Пароли хеширует готовая argon2-cffi (Argon2id со случайной солью). Сессия: случайный 256-битный токен, в базе только его SHA-256; 7 дней после входа, анонимная форма — 1 час. Вход и выход меняют токен и CSRF; выход удаляет старую сессию. Защита форм: скрытый случайный CSRF, связанный с серверной сессией, проверка Origin и Sec-Fetch-Site, SameSite cookie. Права проверяются в обработчиках, заказ ищется сразу по `id` **и** `user_id`. Есть ограничения полей, размера тела и попыток входа (10 на email, 100 на IP за 15 минут), одновременно выполняются не более двух операций Argon2. За fallback Nginx виден loopback, поэтому IP-ограничение на этом VDS является общим; поддельный X-Forwarded-For не принимается. Все значения SQL передаются плейсхолдерами.

## Обработчики

Автоматическая документация: https://rustkoff.ru/docs, схема: `/openapi.json`.

| Метод и путь | Назначение |
| --- | --- |
| GET `/`, `/index.html`, `/catalog.html`, `/<slug>.html` | серверные страницы с данными SQLite; прежние 12 товарных URL сохранены |
| GET `/api/products`, `/api/products/{id}` | список и отдельный товар JSON |
| POST `/register`, `/login`, `/logout` | учётная запись и сессии; поля form-urlencoded, CSRF |
| GET `/account.html`, `/api/me` | вход/регистрация или профиль; API требует входа |
| GET `/cart.html`, `/api/cart` | интерфейс корзины и закрытые данные |
| POST `/cart/add`, `/cart/update` | добавление, изменение; 0 при update удаляет позицию |
| POST `/orders` | создать учебный заказ из своей корзины |
| GET `/order.html?id=…`, `/api/orders/{id}` | свой заказ; чужой/отсутствующий — 404 |
| POST `/feedback` | сохранить сообщение вошедшего пользователя без отправки email |
| GET/HEAD `/health` | проверка HTTP и доступа к БД |

Успех форм приводит к 303 (POST/Redirect/GET), обратная связь показывает результат сохранения. Ошибки: 401 — нужен вход/неверный пароль, 403 — CSRF/Origin, 404 — элемент недоступен, 409 — повторный email/пустая корзина, 422 — неверные данные, 429 — ограничение входов. Проверка полей браузером помогает пользователю, но не заменяет серверную.

## Проверки

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/playwright install --with-deps chromium
# При запущенном локальном сервере:
.venv/bin/python scripts/check_browser.py
```

Серверные тесты работают с временной SQLite, не трогая рабочую базу. Браузерный скрипт создаёт учебную запись и заказ на выбранном `CHECK_URL` (по умолчанию localhost), снимки кладёт в `CHECK_OUTPUT` (по умолчанию tmp). Для опубликованного сайта его не следует запускать без понимания создания данных. `scripts/check_deployment.py` дополнительно перезапускает и пересоздаёт **только контейнер магазина**, проверяет постоянные данные, TLS и удаляет свои две записи; это эксплуатационный тест, а не пассивная проверка.

Фактические результаты и ограничения: `docs/pr3-checks.md`, `docs/pr4-checks.md`. Пояснения к защите: `docs/pr3-notes.md`, `docs/pr4-notes.md`. Сводка требований — `docs/pr3-pr4-requirements.md`. Проверки ПР 1–2 и их снимки сохранены отдельно.

## Каталоги и общий отчёт

```text
app/                  FastAPI, доступ к SQLite, схема и 15 начальных товаров
site/                 Jinja HTML-шаблоны и общий CSS
site/js/              фильтры, калькулятор, обратная связь, курсы валют
site/images/          прежние фотографии и логотип
scripts/              проверки браузера/публикации, резервное копирование, отчёт
tests/                серверные сценарии на временной SQLite
deploy/               фрагменты существующего Nginx
data/                 исходные методички и шаблоны (не изменялись)
docs/                 задания, пояснения, проверки и общий DOCX
docs/report-assets/   исторические снимки ПР 1–2 и отдельные pr3/, pr4/
```

Общий отчёт: `docs/Отчет_Шустов_ЗН251.docx`. ПР 1–2 сохранены как описание предыдущих этапов, добавлены ПР 3–4, результаты, иллюстрации и инструкции. Источники товаров — `docs/product-sources.md`; фотографии и оговорки новых позиций — `docs/photos.md`.

Для воспроизведения подготовки отчёта установите `requirements-dev.txt`, LibreOffice Writer, Poppler и шрифты Liberation. `scripts/extend_report.py` дополняет DOCX, сохраняя ПР 1–2; `scripts/check_report.py` рендерит PDF, обновляет кеш поля содержания и проверяет номера страниц. PNG всех страниц остаются в игнорируемом `tmp/report-render/`. После генерации обязателен визуальный просмотр — скрипт его не заменяет. `scripts/make_report_figures.py` использует сохранённые результаты публикации и делает новые публичные снимки; это инструмент подготовки отчёта на данном VDS.

"""SQLite: соединение на операцию, внешние ключи и атомарные транзакции."""
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@contextmanager
def database():
    path = Path(os.environ.get('DATABASE_PATH', ROOT / 'var/shop.sqlite3'))
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys=ON')
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize():
    with database() as db:
        db.executescript((ROOT / 'app/schema.sql').read_text())
        # INSERT OR IGNORE не заменяет существующий каталог при перезапуске.
        for p in json.loads((ROOT / 'app/products.json').read_text()):
            db.execute('''INSERT OR IGNORE INTO products
                (id,slug,name,short_name,category,unit,price,image,description,specs,source,image_note)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                (p['id'],p['slug'],p['name'],p['short_name'],p['category'],p['unit'],
                 p['price'],p['image'],p['description'],json.dumps(p['specs'],ensure_ascii=False),
                 p['source'],p.get('image_note','')))


def product_dict(row):
    result = dict(row)
    result['specs'] = json.loads(result['specs'])
    return result


def products():
    with database() as db:
        return [product_dict(r) for r in db.execute('SELECT * FROM products ORDER BY id')]


def cart(user_id):
    with database() as db:
        return [dict(r) for r in db.execute('''SELECT p.*, c.quantity,
            p.price*c.quantity AS subtotal FROM cart_items c
            JOIN products p ON p.id=c.product_id WHERE c.user_id=? ORDER BY p.id''',(user_id,))]

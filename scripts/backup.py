"""Согласованная копия SQLite, включая WAL; не копируйте только открытый .sqlite3."""
import argparse
import os
import sqlite3
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--database', required=True, type=Path)
parser.add_argument('--output', required=True, type=Path)
args = parser.parse_args()
os.umask(0o077)
if args.output.exists():
    parser.error('Файл копии уже существует; выберите новое имя.')
args.output.parent.mkdir(parents=True, exist_ok=True)
with sqlite3.connect(args.database.resolve().as_uri()+'?mode=ro', uri=True) as source:
    with sqlite3.connect(args.output) as target:
        source.backup(target)
        assert target.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
args.output.chmod(0o600)
print(f'Копия создана, integrity_check=ok: {args.output}')

#!/bin/sh
set -eu
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock

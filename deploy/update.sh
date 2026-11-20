#!/usr/bin/env bash
# Обновление: git pull в папке с репозиторием, затем sudo bash deploy/update.sh
set -euo pipefail
APP=/opt/hashfan; SRC="$(cd "$(dirname "$0")/.." && pwd)"
rsync -a --exclude .git --exclude .env --exclude '*.db' --exclude .venv "$SRC/" "$APP/"
"$APP/.venv/bin/pip" install -q -r "$APP/requirements.txt"
chown -R hashfan:hashfan "$APP"
systemctl restart hashfan && echo "Обновлено"

#!/usr/bin/env bash
# Обновление: git pull в папке с репозиторием, затем sudo bash deploy/update.sh
set -euo pipefail
APP=/opt/hashfan; SRC="$(cd "$(dirname "$0")/.." && pwd)"
rsync -a --exclude .git --exclude .env --exclude '*.db' --exclude .venv "$SRC/" "$APP/"
"$APP/.venv/bin/pip" install -q -r "$APP/requirements.txt"
chown -R hashfan:hashfan "$APP"
chmod 600 "$APP/.env" "$APP"/*.db 2>/dev/null || true   # личные данные — только для сервиса
# обновляем unit-файл, если он изменился
if ! cmp -s "$SRC/deploy/hashfan.service" /etc/systemd/system/hashfan.service; then
  cp "$SRC/deploy/hashfan.service" /etc/systemd/system/hashfan.service && systemctl daemon-reload
fi
systemctl restart hashfan && echo "Обновлено"

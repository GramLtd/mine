#!/usr/bin/env bash
# Установка TonCry на Ubuntu 22.04/24.04. Запуск: sudo bash deploy/install.sh your-domain.com
set -euo pipefail
DOMAIN="${1:?Укажите домен: sudo bash deploy/install.sh example.com}"
APP=/opt/hashfan
SRC="$(cd "$(dirname "$0")/.." && pwd)"

apt-get update
apt-get install -y python3 python3-venv nginx certbot python3-certbot-nginx rsync

id hashfan &>/dev/null || useradd -r -s /usr/sbin/nologin -d "$APP" hashfan
mkdir -p "$APP"
rsync -a --exclude .git --exclude .env --exclude '*.db' "$SRC/" "$APP/"
[ -f "$APP/.env" ] || { cp "$APP/.env.example" "$APP/.env"; sed -i "s#^WEBAPP_URL=.*#WEBAPP_URL=https://$DOMAIN#" "$APP/.env"; }

python3 -m venv "$APP/.venv"
"$APP/.venv/bin/pip" install -q -r "$APP/requirements.txt"
chown -R hashfan:hashfan "$APP"; chmod 600 "$APP/.env"

cp "$APP/deploy/hashfan.service" /etc/systemd/system/
sed "s/DOMAIN/$DOMAIN/g" "$APP/deploy/nginx.conf" > /etc/nginx/sites-available/hashfan
ln -sf /etc/nginx/sites-available/hashfan /etc/nginx/sites-enabled/hashfan
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --register-unsafely-without-email --redirect

systemctl daemon-reload
systemctl enable hashfan
echo
echo "Готово. Теперь впишите BOT_TOKEN:  sudo nano $APP/.env"
echo "Затем:  sudo systemctl restart hashfan && sudo journalctl -u hashfan -f"

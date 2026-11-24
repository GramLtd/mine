#!/usr/bin/env bash
# Защита сервера. Запуск: sudo bash deploy/harden.sh
# Что делает: ежедневные бэкапы базы, файрвол (SSH + HTTP + HTTPS), fail2ban для SSH,
# автоустановка обновлений безопасности, скрытие версии nginx и лимит размера запросов.
# Ваш текущий SSH-порт определяется автоматически и остаётся открытым — доступ к серверу не потеряется.
set -euo pipefail
SRC="$(cd "$(dirname "$0")/.." && pwd)"
[ "$(id -u)" = 0 ] || { echo "Запустите через sudo"; exit 1; }

echo "== 1/5 Резервные копии базы (каждый день в 04:30) =="
install -m 700 "$SRC/deploy/backup.sh" /usr/local/bin/hashfan-backup
cat > /etc/systemd/system/hashfan-backup.service <<'U'
[Unit]
Description=TonCry database backup
[Service]
Type=oneshot
ExecStart=/usr/local/bin/hashfan-backup
U
cat > /etc/systemd/system/hashfan-backup.timer <<'U'
[Unit]
Description=Daily TonCry database backup
[Timer]
OnCalendar=*-*-* 04:30:00
Persistent=true
[Install]
WantedBy=timers.target
U
systemctl daemon-reload
systemctl enable --now hashfan-backup.timer
/usr/local/bin/hashfan-backup || echo "  (первый бэкап не удался — проверьте, что база существует)"

echo "== 2/5 Пакеты: ufw, fail2ban, unattended-upgrades =="
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ufw fail2ban unattended-upgrades >/dev/null

echo "== 3/5 Файрвол =="
SSH_PORT="$(sshd -T 2>/dev/null | awk '/^port /{print $2; exit}')"
SSH_PORT="${SSH_PORT:-22}"
echo "  SSH-порт: $SSH_PORT (остаётся открытым)"
ufw allow "$SSH_PORT"/tcp >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw --force enable >/dev/null
ufw status | sed 's/^/  /'

echo "== 4/5 fail2ban (бан IP после 5 неудачных входов по SSH на 1 час) =="
cat > /etc/fail2ban/jail.d/hashfan-sshd.conf <<J
[sshd]
enabled = true
port = $SSH_PORT
maxretry = 5
findtime = 10m
bantime = 1h
J
systemctl enable --now fail2ban >/dev/null
systemctl restart fail2ban

echo "== 5/5 Автообновления безопасности и nginx =="
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'A'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
A
if command -v nginx >/dev/null; then
  cat > /etc/nginx/conf.d/hashfan-hardening.conf <<'N'
server_tokens off;           # не показывать версию nginx
client_max_body_size 1m;     # приложению не нужны большие запросы
N
  if nginx -t 2>/dev/null; then systemctl reload nginx; echo "  nginx: ok"
  else rm -f /etc/nginx/conf.d/hashfan-hardening.conf; echo "  nginx: настройка пропущена (конфликт с существующей)"; fi
fi
echo
echo "Готово. Бэкапы: /var/backups/hashfan  ·  Проверить файрвол: sudo ufw status  ·  Баны: sudo fail2ban-client status sshd"

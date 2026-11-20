# TonCry — Telegram-бот + Mini App (idle-майнер)

Игра: вентилятор «майнит» виртуальные монеты, игрок забирает их, улучшает ферму, приглашает друзей и выполняет миссии.

## Запуск
```bash
pip install -r requirements.txt
cp .env.example .env   # вставьте BOT_TOKEN от @BotFather и WEBAPP_URL
python main.py
```
Mini App должен открываться по **HTTPS**. Для теста: `ngrok http 8000` → URL в `WEBAPP_URL`.
В @BotFather можно также сделать `/newapp`, чтобы получить ссылку вида `t.me/bot/app`.

## Telegram Stars
Оплата идёт в валюте `XTR`, провайдер не нужен. Товары и цены — `SHOP` в `app/config.py`
(бусты ×2/×3 на сутки, мгновенный уровень, пакет монет). Повторное начисление по одному
платежу невозможно (уникальный `charge_id`). Команда `/paysupport` есть — Telegram её требует.

## Админ-панель
Совет: после первого входа добавьте свой ID в `ADMIN_IDS` — username можно сменить или потерять,
и тогда доступ получит его новый владелец.

## Структура
- `main.py` — запускает бота (aiogram) и API (FastAPI) в одном процессе
- `app/bot.py` — `/start`, реферальные ссылки `?start=ref<id>`
- `app/server.py` — API: state / claim / upgrade / friends / missions
- `app/auth.py` — проверка подписи Telegram `initData` (подделать запрос нельзя)
- `app/game.py`, `app/config.py` — экономика: уровни, скорость, лимит хранилища
- `webapp/index.html` — интерфейс Mini App

Весь подсчёт монет идёт на сервере; клиент только анимирует счётчик.

## Установка на VPS (Ubuntu)
1. Направьте домен (A-запись) на IP сервера.
2. На сервере:
   ```bash
   git clone -b claude/zealous-turing-41rldm https://github.com/gramltd/mine.git && cd mine
   sudo bash deploy/install.sh your-domain.com
   sudo nano /opt/hashfan/.env          # BOT_TOKEN, ADMIN_IDS
   sudo systemctl restart hashfan
   ```
3. Логи: `sudo journalctl -u hashfan -f`. Обновление: `git pull && sudo bash deploy/update.sh`.
4. Бэкап базы: `/opt/hashfan/game.db`.

## Настройки и выводы
- Админ → «Ещё»: название монеты, текст приветствия `/start` (HTML, `{coin}` — название монеты),
  минимальная сумма вывода (по умолчанию 15), вкл/выкл вывода, рассылка.
- Игрок создаёт заявку на вывод на TON-адрес (адрес проверяется по контрольной сумме), монеты сразу
  списываются. Админ получает уведомление в бот (нужен `ADMIN_IDS`), отправляет TON вручную и
  отмечает «Выплачено» или «Отклонить» (монеты возвращаются).
- Интерфейс админки (`app/admin_ui/admin.html`) отдаётся только админам через `/api/admin/ui`.

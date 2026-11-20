# HashFan — Telegram-бот + Mini App (idle-майнер)

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
Доступ: `ADMIN_USERNAMES` (по умолчанию `ibuybalenciaga`) и `ADMIN_IDS`.
- В приложении появляется вкладка **«Админ»**: статистика, поиск игроков и редактирование
  (баланс, уровень, бан, выдача буста), список платежей с возвратом Stars, рассылка всем.
- В боте: `/admin` — краткая статистика и ваш ID.

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

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

## Структура
- `main.py` — запускает бота (aiogram) и API (FastAPI) в одном процессе
- `app/bot.py` — `/start`, реферальные ссылки `?start=ref<id>`
- `app/server.py` — API: state / claim / upgrade / friends / missions
- `app/auth.py` — проверка подписи Telegram `initData` (подделать запрос нельзя)
- `app/game.py`, `app/config.py` — экономика: уровни, скорость, лимит хранилища
- `webapp/index.html` — интерфейс Mini App

Весь подсчёт монет идёт на сервере; клиент только анимирует счётчик.

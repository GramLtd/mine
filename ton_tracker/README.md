# TON Transfer Tracker Bot

Telegram-бот, который следит за исходящими переводами TON с указанных кошельков
и публикует их в канал (или присылает админам, если автопубликация выключена).

## Запуск
```bash
cd ton_tracker
pip install -r requirements.txt
cp .env.example .env   # впишите BOT_TOKEN и ADMIN_IDS
python main.py
```

## Возможности
- Добавление/удаление кошельков (кнопки или `/add адрес метка`, `/remove адрес`)
- Автопубликация переводов в канал (`/channel @name`, `/autopost on|off`)
- Минимальная сумма для публикации
- Сообщение: от кого, кому, сумма, комментарий, ссылка на Tonviewer

Бот должен быть администратором канала. Данные — toncenter API v3.

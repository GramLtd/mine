"""Перевод текстов для игроков (ru → en). Админка остаётся на русском."""
import contextvars
import re

lang_var: contextvars.ContextVar[str] = contextvars.ContextVar("lang", default="ru")


def norm(code: str | None) -> str:
    code = (code or "").lower()
    return "ru" if code[:2] in ("ru", "uk", "be", "kk", "uz", "ky", "tg", "hy", "az", "ka") else "en"


EN = {
    # ошибки API
    "Вы не подписаны": "You are not subscribed",
    "Вывод временно недоступен": "Withdrawals are temporarily unavailable",
    "Заявка не найдена или уже обработана": "Request not found or already processed",
    "Не удалось проверить подписку": "Could not verify the subscription",
    "Неверный TON-адрес": "Invalid TON address",
    "Недостаточно средств или уже есть заявка в обработке": "Insufficient funds or a request is already pending",
    "Недостаточно средств на балансе": "Insufficient balance",
    "Нет такого товара": "No such item",
    "Оплата в TON временно недоступна": "TON payments are temporarily unavailable",
    "Пополнение — только в TON": "Top-ups are TON only",
    "Скин не куплен": "Skin not purchased",
    "Уже выполнено": "Already completed",
    "Уже получено сегодня": "Already claimed today",
    "Нет доступа": "Access denied",
    "Задание не найдено": "Task not found",
    "Заказ не найден": "Order not found",
    "Пользователь не найден": "User not found",
    "Аккаунт заблокирован": "Account blocked",
    "Ошибка сети": "Network error",
    # покупки
    "Аренда истекла — сначала продлите сервер": "Rental expired — renew the server first",
    "Комиссия уже отключена": "The fee is already disabled",
    "Нет такого сервера": "No such server",
    "Сервер не найден": "Server not found",
    "Скин уже куплен": "Skin already purchased",
    "Уже есть такое или большее хранилище": "You already have this or a bigger storage",
    "Это максимальный тариф": "This is the top plan",
    "Этот сервер закончился, пополнение в 12:00 МСК": "Sold out — restock at 12:00 Moscow time",
    "Отключение комиссии": "Fee removal",
    "Пополнение баланса": "Balance top-up",
    "Сервер закончился на складе — оплата возвращена на баланс": "Server sold out — payment returned to your balance",
    "Товар недоступен — оплата возвращена на баланс": "Item unavailable — payment returned to your balance",
    "Покупка": "Purchase",
    "Звёзды возвращены.": "Stars refunded.",
    # скины
    "Золото": "Gold", "Изумруд": "Emerald", "Рубин": "Ruby", "Лёд": "Ice", "Карбон": "Carbon",
    "Скин вентилятора": "Fan skin",
    "Бегущий блик и искры": "Running shine and sparkles", "Пульсирующее свечение": "Pulsing glow",
    "Огненный обод": "Fiery rim", "Снежинки и иней": "Snowflakes and frost", "Неоновое кольцо": "Neon ring",
    "Ежедневный бонус": "Daily bonus",
}

PATTERNS = [
    (re.compile(r"^Минимальное пополнение — (.+)$"), r"Minimum top-up is \1"),
    (re.compile(r"^Минимум (.+)$"), r"Minimum \1"),
    (re.compile(r"^Сервер (.+)$"), r"Server \1"),
    (re.compile(r"^Улучшение: (.+)$"), r"Upgrade: \1"),
    (re.compile(r"^Продление: (.+)$"), r"Renewal: \1"),
    (re.compile(r"^Сервер (.+)$"), r"Server \1"),
]
SPEC = re.compile(r"(\d+) (?:ядро|ядра|ядер) / (\d+) GB RAM")


def t(text, lang: str | None = None):
    lang = lang or lang_var.get()
    if lang != "en" or not isinstance(text, str):
        return text
    if text in EN:
        return EN[text]
    for rx, rep in PATTERNS:
        if rx.match(text):
            text = rx.sub(rep, text)
            break
    text = SPEC.sub(r"\1 vCPU / \2 GB RAM", text)
    return EN.get(text, text)


def L(lang: str, ru: str, en: str) -> str:
    return en if lang == "en" else ru

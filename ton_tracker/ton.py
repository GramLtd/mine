"""Работа с toncenter API v3."""
import asyncio
import aiohttp
from config import TONCENTER_API_KEY

API = "https://toncenter.com/api/v3"
_lock = asyncio.Lock()


async def _get(path, **params):
    headers = {"X-API-Key": TONCENTER_API_KEY} if TONCENTER_API_KEY else {}
    async with _lock:  # соблюдаем rate-limit
        async with aiohttp.ClientSession() as s:
            for attempt in range(3):
                async with s.get(f"{API}/{path}", params=params, headers=headers,
                                 timeout=aiohttp.ClientTimeout(total=20)) as r:
                    if r.status == 429:
                        await asyncio.sleep(1.5 * (attempt + 1))
                        continue
                    r.raise_for_status()
                    data = await r.json()
                await asyncio.sleep(0.2 if TONCENTER_API_KEY else 1.1)
                return data
    raise RuntimeError("toncenter rate limit")


async def normalize(address: str) -> str | None:
    """Проверяет адрес и возвращает user-friendly (bounceable=false) форму."""
    try:
        data = await _get("addressBook", address=address)
    except aiohttp.ClientResponseError as e:
        if e.status in (400, 422):
            return None
        raise
    for v in data.values():
        return v.get("user_friendly")
    return None


async def transactions(address: str, limit: int = 30):
    """Возвращает (список транзакций по убыванию lt, address_book)."""
    data = await _get("transactions", account=address, limit=limit, sort="desc")
    return data.get("transactions", []), data.get("address_book", {})


def outgoing_transfers(tx, book):
    """Извлекает исходящие TON-переводы из транзакции."""
    if tx.get("description", {}).get("aborted"):
        return []
    res = []
    for m in tx.get("out_msgs", []):
        dest = m.get("destination")
        value = int(m.get("value") or 0)
        if not dest or value <= 0:
            continue
        comment = None
        content = m.get("message_content") or {}
        decoded = content.get("decoded") or {}
        if decoded.get("type") == "text_comment":
            comment = decoded.get("comment")
        res.append({
            "to": book.get(dest, {}).get("user_friendly", dest),
            "amount": value / 1e9,
            "comment": comment,
        })
    return res

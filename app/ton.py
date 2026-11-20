import base64
import re

_RAW = re.compile(r"^-?\d+:[0-9a-fA-F]{64}$")


def _crc16(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return crc


def valid_address(addr: str) -> bool:
    """Проверка TON-адреса: raw (0:abc…) или user-friendly (UQ…/EQ…) с контрольной суммой."""
    addr = addr.strip()
    if _RAW.match(addr):
        return True
    if len(addr) != 48:
        return False
    try:
        raw = base64.urlsafe_b64decode(addr.replace("+", "-").replace("/", "_"))
    except Exception:
        return False
    if len(raw) != 36 or (raw[0] & 0x3F) != 0x11:  # bounceable/non-bounceable (+testnet-флаг)
        return False
    return _crc16(raw[:34]) == int.from_bytes(raw[34:], "big")


# ---------- приём оплаты ----------
import asyncio
import json
import logging
import time
import urllib.parse
import urllib.request

log = logging.getLogger("toncry.ton")
NANO = 1_000_000_000


def transfer_links(address: str, nano: int, comment: str) -> dict:
    q = urllib.parse.urlencode({"amount": nano, "text": comment})
    return {"ton": f"ton://transfer/{address}?{q}",
            "tonkeeper": f"https://app.tonkeeper.com/transfer/{address}?{q}"}


def _fetch_transactions(address: str, limit: int = 50) -> list:
    from .config import TONCENTER_URL, TONCENTER_API_KEY
    url = f"{TONCENTER_URL}/getTransactions?" + urllib.parse.urlencode(
        {"address": address, "limit": limit, "archival": "true"})
    req = urllib.request.Request(url, headers={"X-API-Key": TONCENTER_API_KEY} if TONCENTER_API_KEY else {})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.load(r)
    if not data.get("ok"):
        raise RuntimeError(data.get("error") or "toncenter error")
    return data["result"]


def _incoming(tx) -> tuple[str, int, str] | None:
    """(hash, value_nano, comment) для входящего перевода с текстовым комментарием."""
    m = tx.get("in_msg") or {}
    if not m.get("source"):  # внешнее сообщение, не перевод
        return None
    comment = m.get("message") or ""
    if not comment:
        md = m.get("msg_data") or {}
        if md.get("@type") == "msg.dataText":
            try:
                comment = base64.b64decode(md.get("text", "")).decode("utf-8", "ignore")
            except Exception:
                comment = ""
    if not comment:
        return None
    return tx["transaction_id"]["hash"], int(m.get("value") or 0), comment.strip()


_lock = asyncio.Lock()


async def check_payments(on_paid) -> int:
    """Сверяет последние входящие переводы с ожидающими заказами. on_paid(order) — async-колбэк."""
    from . import db, settings
    from .config import TON_ORDER_TTL
    wallet = settings.ton_wallet()
    if not wallet:
        return 0
    async with _lock:
        orders = {o["comment"]: o for o in db.ton_orders_pending(time.time() - TON_ORDER_TTL * 2)}
        if not orders:
            return 0
        txs = await asyncio.to_thread(_fetch_transactions, wallet)
        n = 0
        for tx in txs:
            inc = _incoming(tx)
            if not inc:
                continue
            h, value, comment = inc
            o = orders.get(comment)
            if not o or value < o["nano"]:
                continue
            if db.ton_order_mark_paid(o["id"], h):
                n += 1
                orders.pop(comment)
                try:
                    await on_paid(db.ton_order_get(o["id"]))
                except Exception:
                    log.exception("on_paid failed for order %s", o["id"])
        return n


async def watcher(on_paid, interval: int = 15):
    while True:
        try:
            await check_payments(on_paid)
        except Exception as e:
            log.warning("TON check failed: %s", e)
        await asyncio.sleep(interval)

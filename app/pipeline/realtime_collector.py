"""SSI FastConnect realtime collector, isolated from API request handlers.

The collector is opt-in and runs as an in-process background task on Render.
It consumes SSI market events through the official async SDK and persists only
the latest tick per symbol in MongoDB. API routes never contact SSI.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, datetime, time, timezone
from typing import Any
from zoneinfo import ZoneInfo

from pymongo import UpdateOne

from app.database.mongo import get_database

logger = logging.getLogger(__name__)
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
SSI_STREAM_BATCH_SIZE = max(1, min(50, int(os.getenv("SSI_STREAM_BATCH_SIZE", "25"))))
FLUSH_INTERVAL_SECONDS = max(1, int(os.getenv("REALTIME_FLUSH_SECONDS", "2")))
MAX_SYMBOLS = max(1, min(500, int(os.getenv("REALTIME_MAX_SYMBOLS", "100"))))
QUEUE_MAXSIZE = max(100, int(os.getenv("REALTIME_QUEUE_MAXSIZE", "2000")))


def realtime_enabled() -> bool:
    return os.getenv("ENABLE_REALTIME_CRAWLER", "false").strip().lower() in {"1", "true", "yes", "on"}


def is_market_window(now: datetime | None = None) -> bool:
    """Vietnam cash-equity sessions: weekdays, 09:00-11:30 and 13:00-15:00."""
    current = now.astimezone(VN_TZ) if now else datetime.now(VN_TZ)
    if current.weekday() >= 5:
        return False
    clock = current.time().replace(tzinfo=None)
    return time(9, 0) <= clock < time(11, 30) or time(13, 0) <= clock < time(15, 0)


def is_after_close(now: datetime | None = None) -> bool:
    current = now.astimezone(VN_TZ) if now else datetime.now(VN_TZ)
    return current.weekday() < 5 and current.time().replace(tzinfo=None) >= time(15, 0)


def chunks(values: list[str], size: int):
    for offset in range(0, len(values), size):
        yield values[offset:offset + size]


def _message_value(message: Any, *names: str) -> Any:
    for name in names:
        if isinstance(message, dict) and name in message:
            return message[name]
        value = getattr(message, name, None)
        if value is not None:
            return value
    return None


def normalize_trade(message: Any, received_at: datetime | None = None) -> dict[str, Any] | None:
    """Convert an SSI TradeMessage into a compact, provider-neutral document."""
    symbol = _message_value(message, "symbol", "s")
    price = _message_value(message, "price", "p")
    if not symbol or price in (None, ""):
        return None
    current = received_at or datetime.now(timezone.utc)
    trading_time = _message_value(message, "trading_time", "tradingTime", "timestamp", "t")
    try:
        numeric_price = float(price)
    except (TypeError, ValueError):
        return None
    if numeric_price <= 0:
        return None

    def number(*keys: str):
        value = _message_value(message, *keys)
        try:
            return float(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None

    return {
        "_id": str(symbol).strip().upper(),
        "symbol": str(symbol).strip().upper(),
        "price": numeric_price,
        "quantity": number("quantity", "q"),
        "average_price": number("average_price", "avg_price", "a"),
        "open": number("open", "open_price", "o"),
        "high": number("high", "high_price", "h"),
        "low": number("low", "low_price", "l"),
        "total_volume": number("total_volume", "total_vol", "v"),
        "side": _message_value(message, "side", "si"),
        "trading_time": str(trading_time) if trading_time else None,
        "trading_date": current.astimezone(VN_TZ).date().isoformat(),
        "updated_at": current,
        "source": "ssi_fastconnect_ws",
    }


def _symbols_from_atlas() -> list[str]:
    db = get_database()
    rows = db.stocks.find({}, {"_id": 0, "symbol": 1}).sort("symbol", 1).limit(MAX_SYMBOLS)
    return list(dict.fromkeys(
        str(row.get("symbol", "")).strip().upper()
        for row in rows if row.get("symbol")
    ))


def _persist_batch(batch: list[dict[str, Any]]) -> int:
    if not batch:
        return 0
    db = get_database()
    operations = [
        UpdateOne(
            {"_id": item["_id"]},
            {"$set": {key: value for key, value in item.items() if key != "_id"},
             "$setOnInsert": {"symbol": item["symbol"]}},
            upsert=True,
        )
        for item in batch
    ]
    result = db.realtime_prices.bulk_write(operations, ordered=False)
    return result.modified_count + len(result.upserted_ids)


async def _flush_worker(queue: asyncio.Queue, stop: asyncio.Event) -> None:
    """Coalesce rapid ticks by symbol and flush bounded batches to Atlas."""
    while not stop.is_set() or not queue.empty():
        latest: dict[str, dict[str, Any]] = {}
        try:
            item = await asyncio.wait_for(queue.get(), timeout=FLUSH_INTERVAL_SECONDS)
            latest[item["_id"]] = item
            while len(latest) < 100:
                try:
                    item = queue.get_nowait()
                    latest[item["_id"]] = item
                except asyncio.QueueEmpty:
                    break
        except asyncio.TimeoutError:
            pass
        if latest:
            try:
                await asyncio.to_thread(_persist_batch, list(latest.values()))
            except Exception:
                logger.exception("Unable to persist SSI realtime batch; latest ticks will be retried only if received again")


def _finalize_daily_candles(trading_day: date) -> int:
    """Publish the last realtime snapshot as D1 candles for this trading day."""
    db = get_database()
    day = trading_day.isoformat()
    count = 0
    cursor = db.realtime_prices.find({"trading_date": day})
    for item in cursor:
        symbol = str(item.get("symbol") or item.get("_id") or "").upper()
        close = item.get("price")
        if not symbol or close is None:
            continue
        candle_id = f"{symbol}:D1:{day}"
        candle = {
            "_id": candle_id,
            "symbol": symbol,
            "interval": "D1",
            "time": day,
            "open": item.get("open") if item.get("open") is not None else close,
            "high": item.get("high") if item.get("high") is not None else close,
            "low": item.get("low") if item.get("low") is not None else close,
            "close": close,
            "volume": item.get("total_volume") or 0,
            "updated_at": datetime.now(timezone.utc),
            "source": "ssi_fastconnect_ws",
        }
        db.price_history.replace_one({"_id": candle_id}, candle, upsert=True)
        count += 1
    return count


async def _run_stream_session() -> None:
    """Connect once, subscribe in bounded symbol groups, and process pushed ticks."""
    from ssi_sdk import AsyncAuth, AsyncStream, Config

    client_id = os.getenv("SSI_CLIENT_ID", "").strip()
    api_key = os.getenv("SSI_API_KEY", "").strip()
    api_secret = os.getenv("SSI_API_SECRET", "").strip()
    if not all((client_id, api_key, api_secret)):
        raise RuntimeError("SSI_CLIENT_ID, SSI_API_KEY and SSI_API_SECRET are required")

    symbols = await asyncio.to_thread(_symbols_from_atlas)
    if not symbols:
        logger.warning("Realtime collector found no stock symbols in Atlas")
        await asyncio.sleep(60)
        return

    config = Config(client_id=client_id, api_key=api_key, api_secret=api_secret)
    queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()

    def on_market_data(message: Any) -> None:
        item = normalize_trade(message)
        if item is None:
            return
        def enqueue() -> None:
            try:
                queue.put_nowait(item)
            except asyncio.QueueFull:
                logger.warning("Realtime tick queue is full; dropping oldest market update")
                try:
                    queue.get_nowait()
                    queue.put_nowait(item)
                except asyncio.QueueEmpty:
                    pass
        loop.call_soon_threadsafe(enqueue)

    async with AsyncAuth(config) as auth:
        # SSI documents market-data authentication without OTP; do not request
        # trading permissions or configure order/trading callbacks.
        await auth.authenticate()
        async with AsyncStream(auth) as stream:
            stream.streaming.on_data = on_market_data
            await stream.streaming.connect()
            for group in chunks(symbols, SSI_STREAM_BATCH_SIZE):
                await stream.streaming.subscribe_symbol_trade(group)
            logger.info("SSI realtime stream connected; subscribed=%s batch_size=%s", len(symbols), SSI_STREAM_BATCH_SIZE)

            flush_task = asyncio.create_task(_flush_worker(queue, stop), name="ssi-realtime-flush")
            try:
                while is_market_window():
                    # SDK wait yields control after a bounded interval so market
                    # hours and shutdown are re-evaluated regularly.
                    await stream.streaming.wait(timeout_ms=5000)
            finally:
                stop.set()
                await flush_task


async def realtime_collector_loop() -> None:
    """Opt-in market-hours loop with bounded reconnect backoff and daily close."""
    retry_seconds = 5
    finalized_days: set[str] = set()
    while True:
        now = datetime.now(VN_TZ)
        try:
            if is_market_window(now):
                retry_seconds = 5
                await _run_stream_session()
                await asyncio.sleep(2)
                continue

            if is_after_close(now):
                day = now.date().isoformat()
                if day not in finalized_days:
                    count = await asyncio.to_thread(_finalize_daily_candles, now.date())
                    finalized_days.add(day)
                    logger.info("Finalized SSI realtime D1 candles for %s: %s symbols", day, count)
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("SSI realtime collector failed; retrying with backoff")
            await asyncio.sleep(retry_seconds)
            retry_seconds = min(120, retry_seconds * 2)

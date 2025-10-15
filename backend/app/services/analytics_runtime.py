from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Set, Tuple
from pathlib import Path

from fastapi import WebSocket

from ..db.models import User, Bot
from . import analytics_service as svc


def _now_ms() -> int:
    return int(time.time() * 1000)


def _parse_timeframe_secs(tf: str) -> int:
    tf = tf.lower()
    if tf.endswith("m"):
        return int(tf[:-1]) * 60
    if tf.endswith("h"):
        return int(tf[:-1]) * 3600
    if tf.endswith("d"):
        return int(tf[:-1]) * 86400
    # default to 5m if unknown
    return 300


@dataclass
class SeriesData:
    pair: str
    timeframe: str
    candles: Any
    indicators: Dict[str, list]
    signals: Dict[str, list]
    updated_ms: int = field(default_factory=_now_ms)


class AnalyticsCollector:
    def __init__(self, user: User, bot: Bot, limit: int = 200) -> None:
        self.user = user
        self.bot = bot
        self.limit = limit
        self._task: Optional[asyncio.Task] = None
        self._stopped = asyncio.Event()
        self._cache_lock = asyncio.Lock()
        self._series: Dict[Tuple[str, str], SeriesData] = {}
        self._pairs: list[str] = []
        self._tfs: list[str] = []

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stopped.clear()
        self._task = asyncio.create_task(self._run(), name=f"collector-bot-{self.bot.id}")

    async def stop(self) -> None:
        self._stopped.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=2)
            except Exception:
                pass

    async def _load_pairs_timeframes(self) -> None:
        # Read config directly from disk
        user_root = Path(self.user.workspace_root).resolve()
        bot_userdir = Path(self.bot.userdir).resolve()
        cfg_path = svc._read_bot_config_path(bot_userdir)
        cfg: dict = {}
        if cfg_path:
            cfg = svc._load_config(cfg_path)
        _, primary_tf = svc._import_strategy(user_root, bot_userdir, cfg)
        pairs: list[str] = []
        try:
            if isinstance(cfg.get("pairs"), list):
                pairs = cfg.get("pairs") or []
            elif isinstance(cfg.get("pair_whitelist"), list):
                pairs = cfg.get("pair_whitelist") or []
        except Exception:
            pairs = []
        tfs: list[str] = []
        if primary_tf:
            tfs.append(primary_tf)
        try:
            if isinstance(cfg.get("timeframe"), str) and cfg.get("timeframe") not in tfs:
                tfs.append(cfg.get("timeframe"))
        except Exception:
            pass
        if not tfs:
            tfs = ["5m"]
        self._pairs = pairs
        self._tfs = tfs

    async def _run(self) -> None:
        await self._load_pairs_timeframes()
        # Basic interval loop; fetch all series every cadence with small sleep to reduce burst
        # Cadence: min of timeframe seconds across tfs, bounded between 15s and 60s
        min_tf = min(_parse_timeframe_secs(tf) for tf in (self._tfs or ["60s"]))
        cadence = max(15, min(60, min_tf // 2))
        while not self._stopped.is_set():
            try:
                await self._tick()
            except Exception:
                pass
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=cadence)
            except asyncio.TimeoutError:
                pass

    async def _tick(self) -> None:
        # Recompute all series (simple and robust for v1)
        user_root = Path(self.user.workspace_root).resolve()
        bot_userdir = Path(self.bot.userdir).resolve()
        cfg_path = svc._read_bot_config_path(bot_userdir)
        cfg: dict = {}
        if cfg_path:
            cfg = svc._load_config(cfg_path)
        strategy_cls, _ = svc._import_strategy(user_root, bot_userdir, cfg)
        updates: list[SeriesData] = []
        for pair in self._pairs:
            for tf in self._tfs:
                try:
                    candles = svc.fetch_candles(self.bot, pair, tf, limit=self.limit)
                    df, _err = svc._df_from_candles(candles)
                    indicators: dict[str, list] = {}
                    signals: dict[str, list] = {}
                    if df is not None:
                        sdf = svc._apply_strategy(strategy_cls, tf, df)
                        if sdf is not None:
                            base_cols = {"date", "open", "high", "low", "close", "volume"}
                            try:
                                import pandas as pd  # type: ignore
                                for col in sdf.columns:
                                    if col not in base_cols:
                                        try:
                                            indicators[col] = [None if pd.isna(v) else float(v) for v in sdf[col].tolist()]
                                        except Exception:
                                            pass
                                for col in ("buy", "sell", "enter_long", "exit_long"):
                                    if col in sdf.columns:
                                        try:
                                            signals[col] = [bool(v) if v in (0, 1, True, False) else False for v in sdf[col].tolist()]
                                        except Exception:
                                            pass
                            except Exception:
                                pass
                    sd = SeriesData(pair=pair, timeframe=tf, candles=candles, indicators=indicators, signals=signals)
                    updates.append(sd)
                except Exception:
                    continue
        if not updates:
            return
        async with self._cache_lock:
            for sd in updates:
                self._series[(sd.pair, sd.timeframe)] = sd
        await broadcast_updates(self.bot.id, updates)

    async def snapshot(self) -> dict:
        async with self._cache_lock:
            series = [
                {
                    "pair": k[0],
                    "timeframe": k[1],
                    "candles": v.candles,
                    "indicators": v.indicators,
                    "signals": v.signals,
                }
                for k, v in self._series.items()
            ]
            return {
                "pairs": self._pairs,
                "timeframes": self._tfs,
                "series": series,
            }


# Registry and WebSocket clients per bot
_collectors: Dict[int, AnalyticsCollector] = {}
_ws_clients: Dict[int, Set[WebSocket]] = {}
_ws_lock = asyncio.Lock()


def get_or_create_collector(user: User, bot: Bot) -> AnalyticsCollector:
    c = _collectors.get(bot.id)
    if c:
        return c
    c = AnalyticsCollector(user, bot)
    _collectors[bot.id] = c
    return c


def start_collector(user: User, bot: Bot) -> None:
    # Fire-and-forget task on event loop
    c = get_or_create_collector(user, bot)
    c.start()


async def stop_collector(bot_id: int) -> None:
    c = _collectors.get(bot_id)
    if not c:
        return
    await c.stop()
    _collectors.pop(bot_id, None)


async def snapshot_from_runtime(user: User, bot: Bot) -> Optional[dict]:
    c = _collectors.get(bot.id)
    if not c:
        return None
    return await c.snapshot()


async def register_ws(bot_id: int, ws: WebSocket) -> None:
    await ws.accept()
    async with _ws_lock:
        if bot_id not in _ws_clients:
            _ws_clients[bot_id] = set()
        _ws_clients[bot_id].add(ws)


async def unregister_ws(bot_id: int, ws: WebSocket) -> None:
    async with _ws_lock:
        try:
            _ws_clients.get(bot_id, set()).discard(ws)
        except Exception:
            pass
    try:
        await ws.close()
    except Exception:
        pass


async def broadcast_updates(bot_id: int, updates: list[SeriesData]) -> None:
    async with _ws_lock:
        clients = list(_ws_clients.get(bot_id, set()))
    if not clients:
        return
    payload = {
        "type": "series",
        "updates": [
            {
                "pair": sd.pair,
                "timeframe": sd.timeframe,
                "candles": sd.candles,
                "indicators": sd.indicators,
                "signals": sd.signals,
            }
            for sd in updates
        ],
    }
    data = json.dumps(payload)
    for ws in clients:
        try:
            await ws.send_text(data)
        except Exception:
            try:
                await unregister_ws(bot_id, ws)
            except Exception:
                pass

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, WebSocket
import os
from sqlalchemy.orm import Session
import asyncio, json

from ..auth import get_current_user, get_db
from ..db.models import User, Bot
from ..db.database import SessionLocal
from ..services import analytics_service as svc
from ..services import analytics_runtime as rt
# app/routes/analytics.py
from starlette.websockets import WebSocketDisconnect
import asyncio
router = APIRouter()


def _get_user(db: Session, user_id: int) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/{user_id}/bots/{bot_id}/analytics/snapshot")
async def analytics_snapshot(user_id: int, bot_id: int, limit: int = 200, current=Depends(get_current_user), db: Session = Depends(get_db)):
    user = _get_user(db, user_id)
    if current.id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.user_id == user.id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    # Standard snapshot path; parity endpoint remains available separately if desired
    # Prefer runtime cache if collector running
    cached = None
    try:
        cached = await rt.snapshot_from_runtime(user, bot)
    except Exception:
        cached = None
    # Use runtime cache only if it contains series; otherwise fall back to direct snapshot
    try:
        if isinstance(cached, dict):
            series = cached.get('series')
            if isinstance(series, list) and len(series) > 0:
                # Merge: use cached series, but ensure open_trades/balance/profit/performance/trades are included
                base = svc.snapshot(db, user, bot, limit=limit)
                try:
                    if isinstance(base, dict):
                        base['series'] = series
                        # Prefer cached pairs/timeframes if present
                        cp = cached.get('pairs')
                        ct = cached.get('timeframes')
                        if isinstance(cp, list):
                            base['pairs'] = cp
                        if isinstance(ct, list):
                            base['timeframes'] = ct
                        return base
                except Exception:
                    pass
                return svc.snapshot(db, user, bot, limit=limit)
    except Exception:
        pass
    return svc.snapshot(db, user, bot, limit=limit)


@router.get("/{user_id}/bots/{bot_id}/analytics/candles")
def analytics_candles(user_id: int, bot_id: int, pair: str, timeframe: str, limit: int = 200, current=Depends(get_current_user), db: Session = Depends(get_db)):
    user = _get_user(db, user_id)
    if current.id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.user_id == user.id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    # Try direct proxy to bot API first; if empty or invalid, fall back to parity snapshot
    try:
        payload = svc.fetch_candles(bot, pair=pair, timeframe=timeframe, limit=limit)
        def _has_candles(obj):
            try:
                if isinstance(obj, list):
                    return len(obj) > 0
                if isinstance(obj, dict):
                    data = obj.get('data')
                    return isinstance(data, list) and len(data) > 0
            except Exception:
                return False
            return False
        if _has_candles(payload):
            return payload
    except HTTPException:
        # fall through to parity below
        pass

    # Fallback: Use parity snapshot only when explicitly enabled
    allow_parity = os.environ.get("FT_ANALYTICS_PARITY_ENABLED", "false").lower() == "true"
    if allow_parity:
        try:
            res = svc.parity_snapshot(db, user, bot, timeframe=timeframe, limit=limit, pairs=[pair])
            if isinstance(res, dict):
                series = res.get('series')
                if isinstance(series, list) and series:
                    entry = None
                    for s in series:
                        if isinstance(s, dict) and s.get('pair') == pair and s.get('timeframe') == timeframe:
                            entry = s
                            break
                    if entry is None:
                        entry = series[0]
                    return entry.get('candles', [])
        except Exception:
            pass
    # As a last resort, return empty list (do not bubble an upstream connection error to the client)
    return []


@router.get("/{user_id}/bots/{bot_id}/analytics/snapshot/parity")
def analytics_snapshot_parity(
    user_id: int,
    bot_id: int,
    timeframe: str | None = None,
    limit: int = 200,
    pairs: str | None = None,
    from_ts: int | None = None,
    to_ts: int | None = None,
    force: bool | None = False,
    current=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = _get_user(db, user_id)
    if current.id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.user_id == user.id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    # Parse pairs if provided as comma-separated
    pair_list = None
    try:
        if pairs:
            toks = [p.strip() for p in pairs.split(',')]
            pair_list = [p for p in toks if p]
    except Exception:
        pair_list = None
    # Only allow parity snapshot when explicitly enabled or forced via query param
    allow_parity = os.environ.get("FT_ANALYTICS_PARITY_ENABLED", "false").lower() == "true"
    if not allow_parity and not force:
        # Return empty series to signal disabled parity snapshot
        return {"pairs": [], "timeframes": [], "series": []}
    # Use parity snapshot inside docker for maximum strategy fidelity
    return svc.parity_snapshot(
        db,
        user,
        bot,
        timeframe=timeframe,
        limit=limit,
        pairs=pair_list,
        from_ts=from_ts,
        to_ts=to_ts,
    )




@router.websocket("/{user_id}/bots/{bot_id}/analytics/ws")
async def analytics_ws(websocket: WebSocket, user_id: int, bot_id: int):
    # (Optional) log Origin to debug CORS
    try:
        origin = websocket.headers.get('origin')
        # print(f"[ws] origin={origin}")  # or use logging
    except Exception:
        origin = None

    # Fast user/bot lookup
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            await websocket.close(code=4404)
            return
        bot = db.query(Bot).filter(Bot.id == bot_id, Bot.user_id == user.id).first()
        if not bot:
            await websocket.close(code=4404)
            return
    finally:
        try:
            db.close()
        except Exception:
            pass

    # Start the collector if not running
    try:
        rt.start_collector(user, bot)
    except Exception:
        pass

    # Accept the socket *once* and register it
    # rt.register_ws() calls accept() already, but we’ll be defensive
    try:
        await rt.register_ws(bot.id, websocket)
    except RuntimeError:
        # If register_ws didn't accept, accept here
        try:
            await websocket.accept()
        except Exception:
            # If we still can't accept, close out
            try:
                await websocket.close(code=1011)
            except Exception:
                pass
            return
        # Now register (without re-accepting) if needed
        try:
            await rt.register_ws(bot.id, websocket)
        except Exception:
            pass

    # Keep the connection open; we don’t need to read from client
    try:
        while True:
            await asyncio.sleep(30)
    except WebSocketDisconnect:
        pass
    finally:
        await rt.unregister_ws(bot.id, websocket)


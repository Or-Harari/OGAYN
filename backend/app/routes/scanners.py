"""
API routes for market scanner configuration management
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user, get_db
from ..db.models import User
from ..market_scanner.schemas import (
    ScannerConfigCreate,
    ScannerConfigResponse,
    ScannerConfigUpdate,
    ScannerResultSummary,
    ScannerConfigInternal,
)
from ..market_scanner.services.market_repository import MarketRepository
from ..market_scanner.services.market_cache_repository import MarketCacheRepository
from ..market_scanner.services.market_scanner_service import MarketScannerService
from ..market_scanner.services.pairlist_service import PairlistService
from ..market_scanner.services.scanner_config_repository import ScannerConfigRepository
from ..market_scanner.services.scanner_output_repository import ScannerOutputRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/scanners", tags=["Market Scanner"])


def _to_scanner_response(config: Any) -> ScannerConfigResponse:
    """Map DB model to API response with config_json fields expanded."""
    internal = ScannerConfigInternal.from_db_model(config)
    return ScannerConfigResponse(
        id=internal.id,
        user_id=internal.user_id,
        name=internal.name,
        exchange=internal.exchange,
        market_type=internal.market_type,
        enabled=internal.enabled,
        interval_minutes=internal.interval_minutes,
        quote_asset=internal.quote_asset,
        max_pairs=internal.max_pairs,
        min_market_score=internal.min_market_score,
        include_symbols=internal.include_symbols,
        exclude_symbols=internal.exclude_symbols,
        scoring_weights=internal.scoring_weights,
        scoring_thresholds=internal.scoring_thresholds,
        recent_activity=internal.recent_activity,
        recent_activity_thresholds=internal.recent_activity_thresholds,
        output_base_path=internal.output_base_path,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


@router.get("/users/{user_id}/scanners", response_model=list[ScannerConfigResponse])
async def list_user_scanners(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all scanner configurations for a user."""
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Cannot access other users' scanners")
    
    repo = ScannerConfigRepository()
    configs = repo.list_by_user(db, user_id)
    return [_to_scanner_response(config) for config in configs]


@router.post("/users/{user_id}/scanners", response_model=ScannerConfigResponse, status_code=201)
async def create_scanner(
    user_id: int,
    config: ScannerConfigCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new scanner configuration."""
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Cannot create scanners for other users")
    
    # DEBUG: Log what we received from frontend
    print(f"[DEBUG create_scanner] Received config: {config}")
    print(f"[DEBUG create_scanner] recent_activity: {config.recent_activity}")
    
    repo = ScannerConfigRepository()
    
    # Check if scanner with same name already exists
    existing = repo.get_by_user_and_name(db, user_id, config.name)
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Scanner '{config.name}' already exists for this user"
        )
    
    db_config = repo.create(db, user_id, config)
    return _to_scanner_response(db_config)


@router.get("/users/{user_id}/scanners/{scanner_id}", response_model=ScannerConfigResponse)
async def get_scanner(
    user_id: int,
    scanner_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a specific scanner configuration."""
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Cannot access other users' scanners")
    
    repo = ScannerConfigRepository()
    config = repo.get(db, scanner_id)
    
    if not config or config.user_id != user_id:
        raise HTTPException(status_code=404, detail="Scanner not found")
    
    return _to_scanner_response(config)


@router.put("/users/{user_id}/scanners/{scanner_id}", response_model=ScannerConfigResponse)
async def update_scanner(
    user_id: int,
    scanner_id: int,
    config_update: ScannerConfigUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a scanner configuration."""
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Cannot update other users' scanners")
    
    # DEBUG: Log what we received from frontend
    print(f"[DEBUG update_scanner] Received config_update: {config_update}")
    print(f"[DEBUG update_scanner] recent_activity: {config_update.recent_activity}")
    print(f"[DEBUG update_scanner] config_update dict: {config_update.model_dump(exclude_unset=True)}")
    
    repo = ScannerConfigRepository()
    existing = repo.get(db, scanner_id)
    
    if not existing or existing.user_id != user_id:
        raise HTTPException(status_code=404, detail="Scanner not found")
    
    updated = repo.update(db, scanner_id, config_update)
    
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update scanner")
    
    return _to_scanner_response(updated)


@router.delete("/users/{user_id}/scanners/{scanner_id}", status_code=204)
async def delete_scanner(
    user_id: int,
    scanner_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a scanner configuration."""
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Cannot delete other users' scanners")
    
    repo = ScannerConfigRepository()
    existing = repo.get(db, scanner_id)
    
    if not existing or existing.user_id != user_id:
        raise HTTPException(status_code=404, detail="Scanner not found")
    
    success = repo.delete(db, scanner_id)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete scanner")


@router.get("/users/{user_id}/scanners/{scanner_id}/results/latest")
async def get_scanner_latest_results(
    user_id: int,
    scanner_id: int,
    limit: int = 50,
    min_score: int | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get latest scan results for a specific scanner."""
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Cannot access other users' scanner results")
    
    repo = ScannerConfigRepository()
    config = repo.get(db, scanner_id)
    
    if not config or config.user_id != user_id:
        raise HTTPException(status_code=404, detail="Scanner not found")
    
    market_repo = MarketRepository()
    markets = market_repo.latest_markets(
        db=db,
        scanner_id=scanner_id,
        min_score=min_score,
        limit=limit
    )
    
    return {
        "scanner_id": scanner_id,
        "scanner_name": config.name,
        "markets": [market_repo.to_response_row(m) for m in markets]
    }


@router.get("/users/{user_id}/scanners/{scanner_id}/pairlist")
async def get_scanner_pairlist(
    user_id: int,
    scanner_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get pairlist output for a specific scanner (Freqtrade RemotePairList compatible)."""
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Cannot access other users' scanner pairlists")
    
    # Quick auth check - use direct query to avoid overhead
    from ..db.models import ScannerConfig as ScannerConfigModel
    config = db.query(ScannerConfigModel).filter(
        ScannerConfigModel.id == scanner_id,
        ScannerConfigModel.user_id == user_id
    ).with_entities(ScannerConfigModel.output_base_path).first()
    
    if not config:
        raise HTTPException(status_code=404, detail="Scanner not found")
    
    # Extract just the path string
    output_base_path = config[0] if isinstance(config, tuple) else config.output_base_path
    
    # Close DB session immediately - we're just reading files
    db.close()
    
    # Try to read cached pairlist file
    pairlist_path = Path(output_base_path) / "pairlists" / "remote_pairlist.json"
    
    if not pairlist_path.exists():
        pairlist_path = Path(output_base_path) / "pairlists" / "top_pairs.json"
    
    if not pairlist_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Pairlist not yet generated. Run scanner first."
        )
    
    try:
        # Read file asynchronously to avoid blocking
        import aiofiles
        async with aiofiles.open(pairlist_path, mode='r', encoding='utf-8') as f:
            content = await f.read()
            return json.loads(content)
    except ImportError:
        # Fallback to sync if aiofiles not available
        with open(pairlist_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to read pairlist: {e}")
        raise HTTPException(status_code=500, detail="Failed to read pairlist")


@router.get("/users/{user_id}/scanners/{scanner_id}/outputs")
async def get_scanner_outputs(
    user_id: int,
    scanner_id: int,
    limit: int | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get current scanner outputs from the database.
    This endpoint returns the latest filtered and ranked symbols that meet the scanner's criteria.
    Used by the frontend to display scanner results.
    """
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Cannot access other users' scanner outputs")
    
    # Verify scanner exists and belongs to user
    repo = ScannerConfigRepository()
    config = repo.get(db, scanner_id)
    
    if not config or config.user_id != user_id:
        raise HTTPException(status_code=404, detail="Scanner not found")
    
    # Get scanner outputs
    output_repo = ScannerOutputRepository()
    outputs = output_repo.get_scanner_outputs(db, scanner_id, limit)
    
    # Get latest generation timestamp
    latest_timestamp = output_repo.get_latest_generation_timestamp(db, scanner_id)
    
    return {
        "scanner_id": scanner_id,
        "scanner_name": config.name,
        "generated_at": latest_timestamp,
        "count": len(outputs),
        "outputs": [output_repo.to_response_dict(out) for out in outputs]
    }


@router.get("/users/{user_id}/scanners/{scanner_id}/recent-activity")
async def get_scanner_recent_activity(
    user_id: int,
    scanner_id: int,
    window: str = "1h",
    symbols: str | None = None,
    limit: int | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get latest recent-activity metrics from cache for scanner symbols and selected timeframe."""
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Cannot access other users' scanner activity")

    if window not in {"1h", "4h", "1d"}:
        raise HTTPException(status_code=400, detail="window must be one of: 1h, 4h, 1d")

    repo = ScannerConfigRepository()
    config = repo.get(db, scanner_id)
    if not config or config.user_id != user_id:
        raise HTTPException(status_code=404, detail="Scanner not found")

    scanner_internal = ScannerConfigInternal.from_db_model(config)
    desired_market_type = str(scanner_internal.market_type).lower()

    symbol_filter: set[str] | None = None
    if symbols:
        symbol_filter = {
            s.strip().upper()
            for s in symbols.split(",")
            if s and s.strip()
        }
        if not symbol_filter:
            symbol_filter = None

    cache_repo = MarketCacheRepository()
    latest_ts, rows = cache_repo.get_latest_cache(db)

    if latest_ts == 0 or not rows:
        return {
            "scanner_id": scanner_id,
            "scanner_name": config.name,
            "market_type": desired_market_type,
            "window": window,
            "cache_timestamp": None,
            "count": 0,
            "by_symbol": {},
        }

    by_symbol: dict[str, Any] = {}

    for row in rows:
        symbol = str(row.get("symbol") or "").upper()
        if not symbol:
            continue
        if symbol_filter is not None and symbol not in symbol_filter:
            continue

        raw_data = row.get("raw_data")
        if not isinstance(raw_data, dict):
            raw_data = {}

        row_market_type = str(raw_data.get("market_type") or "futures").lower()
        if row_market_type != desired_market_type:
            continue

        recent_activity = raw_data.get("recent_activity")
        if not isinstance(recent_activity, dict):
            recent_activity = {}
        windows = recent_activity.get("windows")
        if not isinstance(windows, dict):
            windows = {}
        window_data = windows.get(window)
        if not isinstance(window_data, dict):
            window_data = {}

        by_symbol[symbol] = {
            "symbol": symbol,
            "market_type": row_market_type,
            "source": recent_activity.get("source"),
            "mode": recent_activity.get("mode"),
            "updated_at": recent_activity.get("updated_at"),
            "stale_after_seconds": recent_activity.get("stale_after_seconds"),
            "window": window,
            "quote_volume": window_data.get("quote_volume"),
            "trade_count": window_data.get("trade_count"),
            "window_updated_at": window_data.get("updated_at"),
            "stale": bool(window_data.get("stale", True)),
        }

        if limit is not None and len(by_symbol) >= max(1, min(1000, limit)):
            break

    return {
        "scanner_id": scanner_id,
        "scanner_name": config.name,
        "market_type": desired_market_type,
        "window": window,
        "cache_timestamp": latest_ts,
        "count": len(by_symbol),
        "by_symbol": by_symbol,
    }


@router.get("/users/{user_id}/outputs")
async def get_user_scanner_outputs(
    user_id: int,
    scanner_id: int | None = None,
    limit: int | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get scanner outputs for all of a user's scanners, or filter by scanner_id.
    Used by the frontend to display all scanner results in one view.
    """
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Cannot access other users' scanner outputs")
    
    output_repo = ScannerOutputRepository()
    outputs = output_repo.get_user_scanner_outputs(db, user_id, scanner_id, limit)
    
    return {
        "user_id": user_id,
        "scanner_id": scanner_id,
        "count": len(outputs),
        "outputs": [output_repo.to_response_dict(out) for out in outputs]
    }



@router.post("/users/{user_id}/scanners/{scanner_id}/run")
async def run_scanner_now(
    user_id: int,
    scanner_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Trigger an immediate scan for a specific scanner."""
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Cannot run other users' scanners")
    
    # Verify scanner exists and user owns it
    from ..db.models import ScannerConfig as ScannerConfigModel
    config = db.query(ScannerConfigModel).filter(
        ScannerConfigModel.id == scanner_id,
        ScannerConfigModel.user_id == user_id
    ).with_entities(ScannerConfigModel.id).first()
    
    if not config:
        raise HTTPException(status_code=404, detail="Scanner not found")
    
    # Close DB session before running scan
    db.close()
    
    try:
        # Use the scheduler's run_scanner_now method for consistency
        from ..market_scanner.background_services import scanner_scheduler
        result = await scanner_scheduler.run_scanner_now(scanner_id)
        return result
            
    except Exception as e:
        logger.exception(f"Failed to run scanner {scanner_id}")
        raise HTTPException(status_code=500, detail=str(e))


# ============== System Status Endpoints ==============

@router.get("/status/fetcher")
async def get_fetcher_status(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get WebSocket market data fetcher service status."""
    try:
        from ..market_scanner.background_services import websocket_fetcher
        from ..market_scanner.services.market_cache_repository import MarketCacheRepository
        
        fetcher_status = websocket_fetcher.get_status()
        
        # Get cache stats
        cache_repo = MarketCacheRepository()
        cache_stats = cache_repo.get_cache_status(db)
        
        return {
            "fetcher_type": "websocket",
            **fetcher_status,
            "cache": cache_stats
        }
    except Exception as e:
        logger.error(f"Error in get_fetcher_status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/scheduler")
async def get_scheduler_status(current_user: User = Depends(get_current_user)):
    """Get scanner scheduler service status."""
    from ..market_scanner.background_services import scanner_scheduler
    return scanner_scheduler.status()


# ============== Legacy Endpoints (for backward compatibility) ==============

@router.get("/status")
async def get_scanner_status():
    """Get scanner runtime status (legacy)."""
    from .scanner_runtime import scanner_runtime
    return scanner_runtime.service.status


@router.post("/run", status_code=202)
async def trigger_scan():
    """Trigger immediate scan (legacy - runs default scanner)."""
    from .scanner_runtime import scanner_runtime
    asyncio.create_task(scanner_runtime.run_once())
    return {"status": "scanning", "message": "Scan triggered"}


@router.post("/run-multi", status_code=202)
async def trigger_multi_scan():
    """Trigger immediate multi-scanner scan."""
    from .scanner_runtime import scanner_runtime
    asyncio.create_task(scanner_runtime.run_multi_scanner())
    return {"status": "scanning", "message": "Multi-scanner run triggered"}

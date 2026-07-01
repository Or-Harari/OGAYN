from __future__ import annotations

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..auth import get_current_user, get_db
from ..market_scanner.services.market_repository import MarketRepository
from ..market_scanner.services.scanner_runtime import scanner_runtime

router = APIRouter(prefix="/markets", tags=["markets"])
repo = MarketRepository()


@router.get("")
def get_markets(
    limit: int = Query(default=200, ge=1, le=1000),
    minScore: int | None = Query(default=None, ge=0, le=100),
    current=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ = current
    rows = repo.latest_markets(db=db, min_score=minScore, limit=limit)
    return [repo.to_response_row(r) for r in rows]


@router.get("/top")
def get_top_markets(
    limit: int = Query(default=50, ge=1, le=1000),
    minScore: int | None = Query(default=None, ge=0, le=100),
    current=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ = current
    rows = repo.top_markets(db=db, limit=limit, min_score=minScore)
    return [repo.to_response_row(r) for r in rows]


@router.get("/history/{symbol}")
def get_market_history(
    symbol: str,
    limit: int = Query(default=200, ge=1, le=5000),
    current=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ = current
    rows = repo.history_for_symbol(db=db, symbol=symbol, limit=limit)
    return [repo.to_response_row(r) for r in rows]


@router.get("/{symbol}")
def get_market_by_symbol(
    symbol: str,
    current=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ = current
    row = repo.latest_for_symbol(db=db, symbol=symbol)
    if not row:
        return {"symbol": symbol.upper(), "found": False}
    payload = repo.to_response_row(row)
    payload["found"] = True
    return payload


@router.post("/scan/run-once")
async def trigger_scan_cycle(current=Depends(get_current_user)):
    _ = current
    result = await scanner_runtime.run_once()
    return result


@router.get("/scan/status")
def get_scanner_status(current=Depends(get_current_user)):
    _ = current
    return scanner_runtime.service.status


# ---- Freqtrade RemotePairList endpoints ----

@router.get("/pairlists")
def list_pairlists(current=Depends(get_current_user)):
    """
    [DEPRECATED] List pairlist files.
    
    This endpoint is deprecated. Use scanner-specific endpoints instead:
    GET /scanners/users/{user_id}/scanners/{scanner_id}/pairlist
    """
    _ = current
    raise HTTPException(
        status_code=410,
        detail="This endpoint is deprecated. Use /scanners/users/{user_id}/scanners/{scanner_id}/pairlist instead."
    )


@router.get("/pairlists/{threshold}")
def get_pairlist(threshold: int, current=Depends(get_current_user)):
    """
    [DEPRECATED] Get a specific pairlist JSON.
    
    This endpoint is deprecated. Pairlists are now generated per scanner.
    Use: GET /scanners/users/{user_id}/scanners/{scanner_id}/pairlist
    """
    _ = current
    raise HTTPException(
        status_code=410,
        detail="This endpoint is deprecated. Use /scanners/users/{user_id}/scanners/{scanner_id}/pairlist instead."
    )


@router.post("/pairlists/generate")
async def trigger_pairlist_generation(current=Depends(get_current_user)):
    """
    [DEPRECATED] Manually trigger pairlist generation.
    
    This endpoint is deprecated. Pairlists are automatically generated when scanners run.
    To manually trigger a scanner run, use: POST /scanners/users/{user_id}/scanners/{scanner_id}/run
    """
    _ = current
    raise HTTPException(
        status_code=410,
        detail="This endpoint is deprecated. Use POST /scanners/users/{user_id}/scanners/{scanner_id}/run instead."
    )

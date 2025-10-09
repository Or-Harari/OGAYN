from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user, get_db
from ..services.strategy_service import discover_strategies, create_strategy_file

router = APIRouter()


@router.get("")
def list_strategies(current=Depends(get_current_user), db: Session = Depends(get_db)):
    # List strategies for current user's workspace
    ws = current.workspace_root
    reg = discover_strategies(ws)
    return sorted(list(reg.keys()))


@router.post("")
def create_strategy(req: dict, current=Depends(get_current_user)):
    class_name = req.get("class_name")
    filename = req.get("filename")
    if not class_name:
        raise HTTPException(status_code=400, detail="class_name required")
    path = create_strategy_file(class_name, filename, current.workspace_root)
    return {"path": path}

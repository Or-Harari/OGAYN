from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import get_current_user, get_db, get_password_hash
from ..db.models import User
from ..schemas import UserCreate, UserRead, MetaUpdateRequest
from ..services.strategy_service import discover_strategies, create_strategy_file
from ..services.config_service import load_meta_config, save_meta_config
from ..services.bot_service import start_bot, stop_bot, bot_status
from ..services.workspace_service import validate_workspace, create_workspace

router = APIRouter()


@router.post("", response_model=UserRead)
def create_user(req: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == req.email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    # Support either explicit workspace_root or a workspace_name to auto-create under default base
    ws: str | None = None
    if getattr(req, "workspace_root", None):
        try:
            ws = validate_workspace(req.workspace_root)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    else:
        name = getattr(req, "workspace_name", None)
        if not name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provide workspace_root or workspace_name")
        ws = create_workspace(name)
    user = User(email=req.email, password_hash=get_password_hash(req.password), workspace_root=ws)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("", response_model=list[UserRead])
def list_users(db: Session = Depends(get_db)):
    return db.query(User).all()


@router.get("/{user_id}/strategies")
def list_user_strategies(user_id: int, current=Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if current.id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    reg = discover_strategies(user.workspace_root)
    return sorted(list(reg.keys()))


@router.post("/{user_id}/strategies")
def create_user_strategy(user_id: int, req: dict, current=Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if current.id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    class_name = req.get("class_name")
    filename = req.get("filename")
    if not class_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="class_name required")
    try:
        path = create_strategy_file(class_name, filename, user.workspace_root)
        return {"path": path}
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.put("/{user_id}", response_model=UserRead)
def update_user(user_id: int, req: dict, current=Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if current.id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    ws = req.get("workspace_root")
    if ws:
        try:
            user.workspace_root = validate_workspace(ws)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    db.commit()
    db.refresh(user)
    return user


@router.get("/{user_id}/config")
def get_user_meta(user_id: int, current=Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if current.id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return load_meta_config(user.workspace_root)


@router.put("/{user_id}/config")
def update_user_meta(user_id: int, req: MetaUpdateRequest, current=Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if current.id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return save_meta_config(req.meta, user.workspace_root)


@router.post("/{user_id}/bot/start")
def start_user_bot(user_id: int, req: dict | None = None, current=Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if current.id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    cfg = (req or {}).get("config_path")
    try:
        rec = start_bot(db, user, cfg)
        return {"status": rec.status, "pid": rec.pid, "config": rec.config_path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{user_id}/bot/stop")
def stop_user_bot(user_id: int, current=Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if current.id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    try:
        rec = stop_bot(db, user)
        return {"status": rec.status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{user_id}/bot/status")
def get_user_bot_status(user_id: int, current=Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if current.id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return bot_status(db, user)

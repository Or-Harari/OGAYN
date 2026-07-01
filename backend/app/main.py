import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routes.strategies import router as strategies_router
from .routes.config import router as config_router
from .routes import users as users_router
from .routes import bots as bots_router
from .routes import auth as auth_router
from .routes import analytics as analytics_router
from .routes import diagnostics as diagnostics_router
from .routes import markets as markets_router
from .routes import scanners as scanners_router
from .db.database import engine
from .db import models
from .market_scanner.services.scanner_runtime import scanner_runtime
from .market_scanner.background_services import websocket_fetcher, scanner_scheduler

import logging

logger = logging.getLogger(__name__)

app = FastAPI(title="FT Strategy Backend")

app.include_router(strategies_router, prefix="/strategies", tags=["strategies"])
# config_router already declares prefix="/config" in its own APIRouter
app.include_router(config_router)
app.include_router(auth_router.router, prefix="/auth", tags=["auth"])
app.include_router(users_router.router, prefix="/users", tags=["users"])
app.include_router(bots_router.router, prefix="/users", tags=["bots"])
app.include_router(analytics_router.router, prefix="/users", tags=["analytics"])
app.include_router(diagnostics_router.router)
app.include_router(markets_router.router)
app.include_router(scanners_router.router)

# CORS configuration based on environment
# In production, frontend and backend are served from same domain (no CORS needed)
# In development, frontend (port 5173) needs to access backend (port 8000)
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

if ENVIRONMENT == "production":
    # Production: No CORS needed (same-origin) or restrict to your domain
    allowed_origins = os.getenv("CORS_ORIGINS", "").split(",") if os.getenv("CORS_ORIGINS") else []
    if allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
        )
else:
    # Development: Allow all origins for local development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Initialize DB
models.Base.metadata.create_all(bind=engine)


@app.on_event("startup")
async def startup_event():
    """Initialize database schema and start background services"""
    models.Base.metadata.create_all(bind=engine)
    from .db.database import _ensure_schema
    _ensure_schema()
    
    # Start WebSocket market data fetcher (real-time, saves every 60 seconds)
    logger.info("Starting WebSocket market data fetcher service...")
    await websocket_fetcher.start(save_interval_seconds=60)
    
    # Start scanner scheduler (auto-runs enabled scanners)
    logger.info("Starting scanner scheduler service...")
    scanner_scheduler.start()
    
    # Start legacy scanner runtime if enabled
    if os.getenv("MARKET_SCANNER_ENABLED", "true").lower() == "true":
        await scanner_runtime.start()
    
    logger.info("All services started successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """Stop all services"""
    logger.info("Stopping services...")
    await websocket_fetcher.stop()
    scanner_scheduler.stop()
    await scanner_runtime.stop()
    logger.info("All services stopped")

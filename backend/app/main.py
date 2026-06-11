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
from .db.database import engine
from .db import models

app = FastAPI(title="FT Strategy Backend")

app.include_router(strategies_router, prefix="/strategies", tags=["strategies"])
# config_router already declares prefix="/config" in its own APIRouter
app.include_router(config_router)
app.include_router(auth_router.router, prefix="/auth", tags=["auth"])
app.include_router(users_router.router, prefix="/users", tags=["users"])
app.include_router(bots_router.router, prefix="/users", tags=["bots"])
app.include_router(analytics_router.router, prefix="/users", tags=["analytics"])
app.include_router(diagnostics_router.router)

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

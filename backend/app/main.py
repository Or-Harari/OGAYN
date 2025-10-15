from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routes.strategies import router as strategies_router
from .routes.config import router as config_router
from .routes import users as users_router
from .routes import bots as bots_router
from .routes import auth as auth_router
from .routes import analytics as analytics_router
from .db.database import engine
from .db import models

app = FastAPI(title="FT Strategy Backend")

app.include_router(strategies_router, prefix="/strategies", tags=["strategies"])
app.include_router(config_router, prefix="/config", tags=["config"])
app.include_router(auth_router.router, prefix="/auth", tags=["auth"])
app.include_router(users_router.router, prefix="/users", tags=["users"])
app.include_router(bots_router.router, prefix="/users", tags=["bots"])
app.include_router(analytics_router.router, prefix="/users", tags=["analytics"])

# Allow local UI/frontends to call the API during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize DB
models.Base.metadata.create_all(bind=engine)

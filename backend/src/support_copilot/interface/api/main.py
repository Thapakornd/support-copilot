from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from support_copilot.core.config import settings
from support_copilot.interface.api.routes import chat, health

app = FastAPI(title="Support Copilot")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health.router)
app.include_router(chat.router)

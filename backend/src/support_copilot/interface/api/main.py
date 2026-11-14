from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from support_copilot.interface.api.routes import chat, health

app = FastAPI(title="Support Copilot")
app.add_middleware(  # ponytail: Vite dev origin only; make configurable for prod
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health.router)
app.include_router(chat.router)

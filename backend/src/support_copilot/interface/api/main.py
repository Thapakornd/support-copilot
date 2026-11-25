import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from support_copilot.application.errors import (
    GenerationUnavailable,
    RetrievalUnavailable,
)
from support_copilot.core.config import settings
from support_copilot.interface.api import errors
from support_copilot.interface.api.routes import articles, chat, health, me, tickets

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await run_in_threadpool(chat.get_answer_question)
    except GenerationUnavailable, RetrievalUnavailable:
        logger.warning(
            "Chat could not initialize at startup. The next request will retry."
        )
    yield


app = FastAPI(title="Support Copilot", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health.router)
app.include_router(chat.router)
app.include_router(me.router)
app.include_router(articles.router)
app.include_router(tickets.router)
errors.register(app)

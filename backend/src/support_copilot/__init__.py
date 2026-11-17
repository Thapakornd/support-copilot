def main() -> None:
    import uvicorn

    from support_copilot.core.config import settings

    uvicorn.run(
        "support_copilot.interface.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload,
    )

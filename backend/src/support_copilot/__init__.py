def main() -> None:
    import uvicorn

    uvicorn.run("support_copilot.interface.api.main:app", reload=True)

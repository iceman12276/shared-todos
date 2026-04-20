from fastapi import FastAPI

app = FastAPI(title="shared-todos")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

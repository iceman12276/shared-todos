from fastapi import FastAPI

from app.auth.oauth import router as oauth_router
from app.auth.router import router as auth_router

app = FastAPI(title="shared-todos")

app.include_router(auth_router)
app.include_router(oauth_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

from fastapi import FastAPI

from app.auth.csrf import CSRFMiddleware
from app.auth.oauth import router as oauth_router
from app.auth.router import router as auth_router
from app.lists.router import router as lists_router
from app.logging_config import configure_logging

configure_logging()

app = FastAPI(title="shared-todos")

app.add_middleware(CSRFMiddleware)
app.include_router(auth_router)
app.include_router(oauth_router)
app.include_router(lists_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

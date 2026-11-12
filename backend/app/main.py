"""ACbridge API entry point. Run with:  uvicorn app.main:app --reload"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.errors import DomainError
from app.routers import admin, artisans, auth, jobs, matching, payments, requests, reviews, skills, verification


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


app = FastAPI(
    title="ACbridge API",
    version="0.1.0",
    description=(
        "Local reputation and service-matching platform for informal artisans.\n\n"
        "**Verification in this prototype is SIMULATED** - no real-world identity or skill assessment is performed."
    ),
    lifespan=lifespan,
)


# Lets the browser-based frontend (a different origin/port) call this API. Auth uses Bearer tokens in a
# header, not cookies, so credentials are not enabled. Set CORS_ORIGINS in .env for your real frontend URL.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(DomainError)
async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "app": "ACbridge"}


for module in (auth, skills, artisans, verification, requests, matching, jobs, payments, reviews, admin):
    app.include_router(module.router)

"""ACbridge API entry point. Run with:  uvicorn app.main:app --reload"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.errors import DomainError
from app.routers import admin, artisans, auth, jobs, matching, requests, reviews, skills, verification


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


# The demo front end (frontend/acbridge.html) may be opened from a file or another port, so allow browser calls.
# Auth uses a bearer header, not cookies, so a wildcard origin is safe here. Restrict CORS_ORIGINS in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(DomainError)
async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "app": "ACbridge"}


for module in (auth, skills, artisans, verification, requests, matching, jobs, reviews, admin):
    app.include_router(module.router)

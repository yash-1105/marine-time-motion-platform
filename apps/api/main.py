import logging
import os
import time
import uuid

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
import redis
from apps.api.core.database import engine

from apps.api.auth.dependencies import require
from apps.api.core.config import settings
from apps.api.routers.alerts import router as alerts_router
from apps.api.routers.analytics import router as analytics_router
from apps.api.routers.audit import router as audit_router
from apps.api.routers.auth import router as auth_router
from apps.api.routers.bottlenecks import router as bottlenecks_router
from apps.api.routers.criticality import router as criticality_router
from apps.api.routers.dashboard import router as dashboard_router
from apps.api.routers.delays import router as delays_router
from apps.api.routers.identity import router as identity_router
from apps.api.routers.ingestion import router as ingestion_router
from apps.api.routers.journey import router as journey_router
from apps.api.routers.kpi import router as kpi_router
from apps.api.routers.operations import router as operations_router
from apps.api.routers.outliers import router as outliers_router
from apps.api.routers.quality import router as quality_router
from apps.api.routers.reporting import router as reporting_router
from apps.api.routers.copilot import router as copilot_router

app = FastAPI(
    title="Marine Time & Motion Platform",
    description="API for the Marine Time & Motion Platform",
    version="1.0.0",
)

cors_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]
if settings.cors_origins:
    cors_origins.extend([origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()])

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger("marine_platform")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(
    logging.Formatter('{"time":"%(asctime)s","level":"%(levelname)s","message":%(message)s}')
)
if not logger.handlers:
    logger.addHandler(handler)


@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    request.state.correlation_id = correlation_id
    started = time.perf_counter()
    # Cookie-backed writes must be same-origin. Bearer-token API clients remain supported.
    if request.method not in {"GET", "HEAD", "OPTIONS"} and request.cookies.get("access_token") and request.headers.get("origin"):
        if request.headers["origin"] not in cors_origins:
            return JSONResponse(status_code=403, content={"code":"CSRF_REJECTED","message":"Cross-origin cookie request rejected","correlation_id":correlation_id})
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'; base-uri 'self'; object-src 'none'"
    if settings.environment != "development":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    logger.info(json_log({"event":"http_request","method":request.method,"path":request.url.path,"status":response.status_code,"latency_ms":round((time.perf_counter()-started)*1000,2),"correlation_id":correlation_id}))
    return response

def json_log(values: dict) -> str:
    import json
    return json.dumps(values, default=str, separators=(",", ":"))


# Public liveness and readiness endpoints
@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/ready")
def readiness_check():
    try:
        with engine.connect() as conn: conn.execute(text("SELECT 1"))
        redis.Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1).ping()
    except Exception:
        return JSONResponse(status_code=503, content={"status":"not_ready"})
    return {"status": "ready", "dependencies": {"postgres":"ok", "redis":"ok"}}


@app.get("/live")
def liveness_check():
    return {"status": "alive"}


# Versioned API Router (/api/v1)
v1_router = APIRouter(prefix="/api/v1")


@v1_router.get("/status")
def status(_=Depends(require("view", "system_status"))):
    return {"version": "v1", "environment": settings.environment}


v1_router.include_router(auth_router)
v1_router.include_router(audit_router)
v1_router.include_router(operations_router)
v1_router.include_router(ingestion_router)
v1_router.include_router(quality_router)
v1_router.include_router(identity_router)
v1_router.include_router(journey_router)
v1_router.include_router(analytics_router)
v1_router.include_router(kpi_router)
v1_router.include_router(delays_router)
v1_router.include_router(bottlenecks_router)
v1_router.include_router(outliers_router)
v1_router.include_router(criticality_router)
v1_router.include_router(alerts_router)
v1_router.include_router(dashboard_router)
v1_router.include_router(reporting_router)
v1_router.include_router(copilot_router)

app.include_router(v1_router)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    correlation_id = getattr(request.state, "correlation_id", "unknown")
    detail = exc.detail
    if isinstance(detail, dict):
        if "correlation_id" not in detail:
            detail["correlation_id"] = correlation_id
        return JSONResponse(status_code=exc.status_code, content=detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": f"HTTP_{exc.status_code}",
            "message": str(detail),
            "correlation_id": correlation_id,
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(json_log({"event":"unhandled_error","path":request.url.path,"correlation_id":getattr(request.state,"correlation_id","unknown")}))
    return JSONResponse(
        status_code=500,
        content={
            "code": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected error occurred",
            "detail": str(exc) if settings.environment == "development" else None,
            "correlation_id": getattr(request.state, "correlation_id", "unknown"),
        },
    )

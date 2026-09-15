import logging
import os
import uuid

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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
if os.getenv("CORS_ORIGINS"):
    cors_origins.extend([origin.strip() for origin in os.getenv("CORS_ORIGINS", "").split(",") if origin.strip()])

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$|^https://.*\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger("marine_platform")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(
    logging.Formatter(
        '{"time": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s", "correlation_id": "%(correlation_id)s"}'
    )
)
logger.addHandler(handler)


@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    request.state.correlation_id = correlation_id
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    return response


# Public liveness and readiness endpoints
@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/ready")
def readiness_check():
    return {"status": "ready"}


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
    return JSONResponse(
        status_code=500,
        content={
            "code": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected error occurred",
            "detail": str(exc),
            "correlation_id": getattr(request.state, "correlation_id", "unknown"),
        },
    )

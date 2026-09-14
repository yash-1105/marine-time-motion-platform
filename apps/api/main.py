import logging
import uuid

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from apps.api.auth.dependencies import require
from apps.api.core.config import settings
from apps.api.routers.audit import router as audit_router
from apps.api.routers.auth import router as auth_router
from apps.api.routers.ingestion import router as ingestion_router
from apps.api.routers.quality import router as quality_router
from apps.api.routers.operations import router as operations_router

app = FastAPI(
    title="Marine Time & Motion Platform",
    description="API for the Marine Time & Motion Platform",
    version="1.0.0",
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

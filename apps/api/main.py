from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import logging
import uuid
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "postgresql://admin:password@localhost:5432/marine_platform"
    redis_url: str = "redis://localhost:6379/0"

settings = Settings()

app = FastAPI(
    title="Marine Time & Motion Platform",
    description="API for the Marine Time & Motion Platform",
    version="1.0.0",
)

logger = logging.getLogger("marine_platform")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('{"time": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s", "correlation_id": "%(correlation_id)s"}'))
logger.addHandler(handler)

@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    request.state.correlation_id = correlation_id
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    return response

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/ready")
def readiness_check():
    return {"status": "ready"}

@app.get("/live")
def liveness_check():
    return {"status": "alive"}

from fastapi import APIRouter
v1_router = APIRouter(prefix="/api/v1")
@v1_router.get("/status")
def status():
    return {"version": "v1"}

app.include_router(v1_router)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "code": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected error occurred",
            "detail": str(exc),
            "correlation_id": getattr(request.state, "correlation_id", "unknown")
        }
    )

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, JSONResponse
from app.api.routes import router as api_router
from app.logging import logger
from contextlib import asynccontextmanager
from app.config import config, BASE_DIR
from app.db.database import Base, engine
import time
from collections import defaultdict

@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(title="VRP Optimizer API", version="2.1.0", lifespan=lifespan)

request_times = defaultdict(list)
RATE_LIMIT = config.RATE_LIMIT_REQUESTS
RATE_WINDOW = config.RATE_LIMIT_WINDOW_SECONDS

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if not request.url.path.startswith("/api/"):
        return await call_next(request)
    client_ip = request.client.host if request.client else "unknown"
    current_time = time.monotonic()
    for ip in list(request_times):
        if not request_times[ip] or current_time - request_times[ip][-1] >= RATE_WINDOW:
            del request_times[ip]

    request_times[client_ip] = [
        t for t in request_times[client_ip] if current_time - t < RATE_WINDOW
    ]

    if len(request_times[client_ip]) >= RATE_LIMIT:
        logger.warning(f"Rate limit exceeded for {client_ip}")
        return JSONResponse(
            content={"detail": "Demasiadas solicitudes. Inténtalo de nuevo en un minuto."},
            status_code=429,
            headers={"Retry-After": str(RATE_WINDOW)},
        )

    request_times[client_ip].append(current_time)
    response = await call_next(request)
    return response

app.include_router(api_router, prefix="/api")

app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")

@app.get("/api/health")
def health():
    return {"status": "ok"}

@app.get("/")
def read_root():
    return RedirectResponse(url="/static/index.html")

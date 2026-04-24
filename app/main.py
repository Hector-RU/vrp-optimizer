from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from app.api.routes import router as api_router
from app.logging import logger
import os
import time
from collections import defaultdict

app = FastAPI(title="VRP Optimizer API")

request_times = defaultdict(list)
RATE_LIMIT = 100
RATE_WINDOW = 60

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    current_time = time.time()
    
    request_times[client_ip] = [
        t for t in request_times[client_ip] if current_time - t < RATE_WINDOW
    ]
    
    if len(request_times[client_ip]) >= RATE_LIMIT:
        logger.warning(f"Rate limit exceeded for {client_ip}")
        return FastAPI.Response(
            content='{"detail":"Rate limit exceeded"}',
            status_code=429,
            media_type="application/json"
        )
    
    request_times[client_ip].append(current_time)
    response = await call_next(request)
    return response

app.include_router(api_router, prefix="/api")

os.makedirs("app/static", exist_ok=True)
os.makedirs("app/static/maps", exist_ok=True)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/")
def read_root():
    return RedirectResponse(url="/static/index.html")

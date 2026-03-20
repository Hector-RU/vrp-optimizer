from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from app.api.routes import router as api_router
import os

app = FastAPI(title="VRP Optimizer API")

app.include_router(api_router, prefix="/api")

# Crea el folder estático si no existe
os.makedirs("app/static", exist_ok=True)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/")
def read_root():
    return RedirectResponse(url="/static/index.html")

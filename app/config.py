import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

class Config:
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{(BASE_DIR / 'vrp.db').as_posix()}")

    VRP_TIME_LIMIT_SECONDS: int = int(os.getenv("VRP_TIME_LIMIT", "30"))
    VRP_SOLVER_STRATEGY: str = os.getenv("VRP_STRATEGY", "PARALLEL_CHEAPEST_INSERTION")

    MAP_OUTPUT_DIR: str = os.getenv("MAP_DIR", str(BASE_DIR / "app" / "static" / "maps"))
    ETA_MODEL_PATH: str = str(Path(__file__).parent / "ml" / "eta_model.joblib")

    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW_SECONDS: int = 60

config = Config()

os.makedirs(config.MAP_OUTPUT_DIR, exist_ok=True)

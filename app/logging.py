import logging
import sys
from app.config import config

def setup_logging():
    logger = logging.getLogger("vrp")
    logger.setLevel(getattr(logging, config.LOG_LEVEL))
    
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(config.LOG_FORMAT))
        logger.addHandler(handler)
    
    return logger

logger = setup_logging()
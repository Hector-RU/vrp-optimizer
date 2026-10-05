import joblib
import os
import datetime
import warnings
from sklearn.exceptions import InconsistentVersionWarning
from app.config import config
from app.logging import logger

MODEL_PATH = config.ETA_MODEL_PATH

class ETAPredictor:
    def __init__(self):
        self.model = None
        self._load_model()

    def _load_model(self):
        if os.path.exists(MODEL_PATH):
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("error", InconsistentVersionWarning)
                    self.model = joblib.load(MODEL_PATH)
            except (OSError, ValueError, EOFError, ImportError, InconsistentVersionWarning):
                logger.warning("No se pudo cargar el modelo ETA; se usará la estimación lineal")
        else:
            print("Warning: ETA model not found. Using fallback linear estimation.")

    def predict_eta(self, distance_km: float, time_of_day: datetime.datetime = None) -> float:
        """
        Predicts the ETA in minutes for a given distance and time.
        """
        if time_of_day is None:
            time_of_day = datetime.datetime(2026, 1, 5, 9)

        if distance_km <= 0:
            return 0.0

        hour = time_of_day.hour
        day_of_week = time_of_day.weekday()

        # The bundled model was trained on synthetic trips from 1 to 50 km.
        # Tree models cannot extrapolate beyond that training range.
        if self.model is not None and 1 <= distance_km <= 50:
             # Scikit-learn expects 2D array, we also provide a DataFrame with feature names to avoid UserWarning
             import pandas as pd
             X_pred = pd.DataFrame([[distance_km, hour, day_of_week]], columns=['distance_km', 'hour', 'day_of_week'])
             prediction = self.model.predict(X_pred)
             return max(0.0, float(prediction[0]))
        else:
             # Fallback estimation if model is not trained yet
             return distance_km * 2.5 + 5.0

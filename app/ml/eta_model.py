import joblib
import os
import datetime

MODEL_PATH = os.path.join(os.path.dirname(__file__), "eta_model.joblib")

class ETAPredictor:
    def __init__(self):
        self.model = None
        self._load_model()

    def _load_model(self):
        if os.path.exists(MODEL_PATH):
            self.model = joblib.load(MODEL_PATH)
        else:
            print("Warning: ETA model not found. Using fallback linear estimation.")

    def predict_eta(self, distance_km: float, time_of_day: datetime.datetime = None) -> float:
        """
        Predicts the ETA in minutes for a given distance and time.
        """
        if time_of_day is None:
            time_of_day = datetime.datetime.now()
            
        hour = time_of_day.hour
        day_of_week = time_of_day.weekday()

        if self.model is not None:
             # Scikit-learn expects 2D array, we also provide a DataFrame with feature names to avoid UserWarning
             import pandas as pd
             X_pred = pd.DataFrame([[distance_km, hour, day_of_week]], columns=['distance_km', 'hour', 'day_of_week'])
             prediction = self.model.predict(X_pred)
             return float(prediction[0])
        else:
             # Fallback estimation if model is not trained yet
             return distance_km * 2.5 + 5.0

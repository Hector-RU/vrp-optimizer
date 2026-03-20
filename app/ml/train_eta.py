import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error
import joblib
import os

MODEL_PATH = os.path.join(os.path.dirname(__file__), "eta_model.joblib")

def generate_synthetic_data(num_samples=5000):
    np.random.seed(42)
    # distance in km (1 to 50)
    distances = np.random.uniform(1, 50, num_samples)
    
    # hour of day (0 to 23)
    hours = np.random.randint(0, 24, num_samples)
    
    # day of week (0=Monday, 6=Sunday)
    days = np.random.randint(0, 7, num_samples)
    
    # Base time: 2 mins per km, plus some fixed overhead
    base_time = distances * 2.0 + 5.0
    
    # Traffic multiplier based on hour (rush hours: 8-10 and 17-19)
    traffic_mult = np.ones(num_samples)
    rush_hour_mask = ((hours >= 8) & (hours <= 10)) | ((hours >= 17) & (hours <= 19))
    traffic_mult[rush_hour_mask] = 1.5
    
    # Weekend multiplier (faster on weekends)
    weekend_mask = (days >= 5)
    traffic_mult[weekend_mask] *= 0.8
    
    # Add random noise
    noise = np.random.normal(0, 2.0, num_samples)
    
    eta = base_time * traffic_mult + noise
    # Ensure no negative times
    eta = np.maximum(eta, distances * 1.0) 
    
    df = pd.DataFrame({
        "distance_km": distances,
        "hour": hours,
        "day_of_week": days,
        "eta_minutes": eta
    })
    
    return df

def train_and_save_model():
    print("Generating synthetic data...")
    df = generate_synthetic_data()
    
    X = df[["distance_km", "hour", "day_of_week"]]
    y = df["eta_minutes"]
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    print("Training ETA model...")
    # Using RandomForest instead of simple linear to capture non-linear rush hour rules easily
    model = RandomForestRegressor(n_estimators=50, random_state=42)
    model.fit(X_train, y_train)
    
    preds = model.predict(X_test)
    mae = mean_absolute_error(y_test, preds)
    print(f"Model trained. MAE on test set: {mae:.2f} minutes")
    
    joblib.dump(model, MODEL_PATH)
    print(f"Model saved to {MODEL_PATH}")

if __name__ == "__main__":
    train_and_save_model()

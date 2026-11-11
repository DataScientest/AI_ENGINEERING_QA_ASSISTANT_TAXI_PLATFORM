"""TaxiFare prediction API: serves the current champion model of the MLflow registry."""
import logging
import os
import threading
import time

import mlflow.sklearn
import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("prediction_api")

MODEL_NAME = "NYC_Taxi_Fare_Model"
MLFLOW_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow_server:5000")
FEATURES = ["vendor_id", "rate_code_id", "pu_location_id", "do_location_id",
            "passenger_count", "pickup_hour", "pickup_dayofweek", "pickup_month", "pickup_weekday"]

model = None
current_model_version = None

app = FastAPI(title="TaxiFare Prediction API")


@app.exception_handler(RequestValidationError)
async def reject_invalid_request(request: Request, exc: RequestValidationError):
    """Invalid input is rejected with 422 and the names of the faulty fields (never their values)."""
    fields = sorted({".".join(str(p) for p in e["loc"][1:]) for e in exc.errors()})
    logger.warning("Rejected invalid request: fields=%s", fields)
    return JSONResponse(status_code=422, content={"detail": "Invalid request", "fields": fields})


class RequestData(BaseModel):
    """Input contract: types AND bounds (NYC TLC zone ids are 1..265)."""
    pickup_longitude: float = Field(0.0, ge=-180, le=180)
    pickup_latitude: float = Field(0.0, ge=-90, le=90)
    dropoff_longitude: float = Field(0.0, ge=-180, le=180)
    dropoff_latitude: float = Field(0.0, ge=-90, le=90)
    passenger_count: float = Field(1.0, ge=1, le=10)
    vendor_id: int = Field(1, ge=1, le=7)
    rate_code_id: float = Field(1.0, ge=1, le=99)
    pu_location_id: int = Field(1, ge=1, le=265)
    do_location_id: int = Field(1, ge=1, le=265)
    pickup_hour: int = Field(12, ge=0, le=23)
    pickup_dayofweek: int = Field(0, ge=0, le=6)
    pickup_month: int = Field(1, ge=1, le=12)
    pickup_weekday: int = Field(1, ge=0, le=1)


def load_champion_model(client=None):
    """Load the model behind the `champion` alias if its version changed. Returns True when a champion exists."""
    global model, current_model_version
    mlflow.set_tracking_uri(MLFLOW_URI)
    if client is None:
        from mlflow.tracking import MlflowClient
        client = MlflowClient(tracking_uri=MLFLOW_URI)
    try:
        new_version = client.get_model_version_by_alias(MODEL_NAME, "champion").version
    except Exception as exc:
        logger.warning("Champion not available yet: %s", exc)
        return False
    if new_version != current_model_version:
        logger.info("Loading champion version %s", new_version)
        model = mlflow.sklearn.load_model(f"models:/{MODEL_NAME}@champion")
        current_model_version = new_version
    return True


def model_polling_loop():
    while True:
        try:
            load_champion_model()
        except Exception as exc:
            logger.error("Error while loading the champion: %s", exc)
        time.sleep(5 if model is None else 60)


@app.on_event("startup")
async def startup_event():
    threading.Thread(target=model_polling_loop, daemon=True).start()


@app.post("/fare_predict")
async def predict(data: RequestData):
    if model is None:
        # Never load a model inside a request: the polling thread retries every 5 s until a champion exists.
        raise HTTPException(status_code=503, detail="Model not yet available")
    input_df = pd.DataFrame([data.model_dump()])[FEATURES]
    try:
        fare = float(model.predict(input_df)[0])
    except Exception as exc:
        logger.error("Prediction error: %s", type(exc).__name__)
        raise HTTPException(status_code=500, detail="Prediction failed")
    return {"predicted_fare": round(fare, 2), "model_version": str(current_model_version)}


SMOKE_ROW = pd.DataFrame([{"vendor_id": 1, "rate_code_id": 1.0, "pu_location_id": 48, "do_location_id": 79,
                            "passenger_count": 1.0, "pickup_hour": 14, "pickup_dayofweek": 2,
                            "pickup_month": 1, "pickup_weekday": 1}])


@app.get("/health")
def health():
    """Readiness: 200 only if a model is loaded AND answers a real prediction."""
    if model is None:
        return JSONResponse(status_code=503, content={"status": "unavailable", "model_loaded": False,
                                                       "reason": "no champion model loaded"})
    try:
        fare = float(model.predict(SMOKE_ROW)[0])
    except Exception as exc:
        logger.error("Health smoke prediction failed: %s", type(exc).__name__)
        return JSONResponse(status_code=503, content={"status": "unavailable", "model_loaded": True,
                                                       "reason": "model cannot predict"})
    return {"status": "ok", "model_loaded": True, "model_version": str(current_model_version),
            "smoke_fare": round(fare, 2)}

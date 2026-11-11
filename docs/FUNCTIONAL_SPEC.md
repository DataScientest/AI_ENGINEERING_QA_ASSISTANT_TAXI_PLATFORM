# TaxiFare platform: functional specification

This document is the reference for the expected behaviour of the platform. A test's expected result comes from here, not from running the code. When the code and this document disagree, that is a finding to report.

Version: `v1.0` of this repository. Ticket ids (`TX-…`) and criterion ids (`AC-…`) refer to the QA Assistant subject of the project catalogue.

## 1. Prediction API (`services/prediction_api/app.py`)

### 1.1 Input contract of `POST /fare_predict`

Every field has a default value, so an empty JSON object is a valid request. Bounds are inclusive.

| Field | Type | Bounds | Default |
| --- | --- | --- | --- |
| `pickup_longitude`, `dropoff_longitude` | float | -180 to 180 | 0.0 |
| `pickup_latitude`, `dropoff_latitude` | float | -90 to 90 | 0.0 |
| `passenger_count` | float | 1 to 10 | 1.0 |
| `vendor_id` | int | 1 to 7 | 1 |
| `rate_code_id` | float | 1 to 99 | 1.0 |
| `pu_location_id`, `do_location_id` | int | 1 to 265 (NYC TLC zones) | 1 |
| `pickup_hour` | int | 0 to 23 | 12 |
| `pickup_dayofweek` | int | 0 (Monday) to 6 | 0 |
| `pickup_month` | int | 1 to 12 | 1 |
| `pickup_weekday` | int | 0 or 1 | 1 |

The model uses 9 features: `vendor_id`, `rate_code_id`, `pu_location_id`, `do_location_id`, `passenger_count`, `pickup_hour`, `pickup_dayofweek`, `pickup_month`, `pickup_weekday`. Coordinates are accepted and ignored.

### 1.2 Responses of `POST /fare_predict`

| Situation | Status | Body | Side effects |
| --- | --- | --- | --- |
| A field is out of bounds or of the wrong type | 422 | `{"detail": "Invalid request", "fields": [<sorted field names>]}` | `invalid_requests_total` +1; one WARNING log line naming the fields, never their values |
| No model loaded | 503 | `{"detail": "Model not yet available"}` | `prediction_errors_total{error_type="model_unavailable"}` +1. The model is never loaded during a request |
| The model raises during inference | 500 | `{"detail": <error text>}` | `prediction_errors_total{error_type="inference_error"}` +1 |
| Valid request, model loaded | 200 | `{"predicted_fare": <float>}` | `prediction_requests_total` +1, fare observed in `prediction_value_dollars`, `total_predicted_revenue_dollars` increased by the fare, prediction remembered for feedback |

Validation happens before the model check: an invalid request returns 422 even when no model is loaded.

### 1.3 Request id and logs

- Every response carries `X-Request-ID`: the value sent by the client in `X-Request-ID`, or a new 32-character hexadecimal id.
- Logs are one JSON object per line with `timestamp`, `level`, `logger`, `message`, `service`, `request_id`, `model_version`, and for request lines `status`, `endpoint`, `duration_ms` (and `trace_id`, `span_id` when tracing is active).
- Request payload values (locations, passengers, fares) never appear in logs.

### 1.4 HTTP metrics

- `http_requests_total{method, endpoint, status}` and `http_request_duration_seconds{method, endpoint}` are recorded for every request except `GET /metrics`.
- `endpoint` is the route template (for example `/fare_predict`). A path that matches no route is labelled `unmatched`, so random paths never create new series.

### 1.5 `GET /health` (readiness)

| Situation | Status | Body |
| --- | --- | --- |
| No model loaded | 503 | `{"status": "unavailable", "model_loaded": false, "reason": "no champion model loaded"}` |
| Model loaded but the smoke prediction raises | 503 | `{"status": "unavailable", "model_loaded": true, "reason": "model cannot predict"}` |
| Model loaded and answers | 200 | `{"status": "ok", "model_loaded": true, "model_version": <str>, "smoke_fare": <fare rounded to 2 decimals>}` |

### 1.6 `POST /feedback` (delayed ground truth)

- Body: `request_id` (string, 1 to 64 characters) and `actual_fare` (strictly between 0 and 5000). Otherwise 422.
- The request id must be one of the last 10,000 successful predictions. The oldest is forgotten first.
- A prediction can receive feedback once. Unknown, expired or already used id: 404 `{"detail": "Unknown or expired request id"}` and `feedback_unmatched_total` +1.
- Success: 200 `{"error": <predicted - actual, rounded to 2 decimals>}`, `labeled_predictions_total` +1 and `prediction_squared_error_dollars2_total` increased by `(predicted - actual)²`.

### 1.7 Fault injection

- `GET /admin/chaos` returns `{"enabled": <bool>, "latency_ms": <int>}`.
- `PUT /admin/chaos` with `{"latency_ms": 0..10000}` returns 403 unless the environment variable `CHAOS_ENABLED` is `true`. When enabled, every prediction waits that long first, in its own span named `downstream_dependency`, and `chaos_latency_seconds` is set to the value in seconds.

### 1.8 Model loading

- The API polls the MLflow registry for the alias `champion` of `NYC_Taxi_Fare_Model`: every 5 s while no model is loaded, every 60 s afterwards.
- A new champion version is loaded once; then `model_loaded` is 1 and `model_version{version=<v>}` is the only version series.

## 2. Data preparation and validation (`services/pipeline/flow.py`, `taxi_validation.py`)

### 2.1 Preparation

- Source columns are renamed: `VendorID`→`vendor_id`, `RatecodeID`→`rate_code_id`, `PULocationID`→`pu_location_id`, `DOLocationID`→`do_location_id`, `Airport_fee`→`airport_fee`.
- Required columns: `vendor_id`, `rate_code_id`, `pu_location_id`, `do_location_id`, `passenger_count`, `tpep_pickup_datetime`, `fare_amount`. If any is missing: `ValueError("Missing required columns: [<sorted names>]")`.
- Derived features: `pickup_hour`, `pickup_dayofweek` (Monday = 0), `pickup_month`, and `pickup_weekday` = 1 from Monday to Friday, 0 on Saturday and Sunday.
- `total_fare` = `fare_amount` + `extra` + `mta_tax` + `improvement_surcharge` + `tolls_amount` + `airport_fee`. Optional components that are absent or empty count as 0.

### 2.2 Validation and quarantine

- Valid ranges (inclusive): `vendor_id` 1-7, `rate_code_id` 1-99, `pu_location_id` and `do_location_id` 1-265, `passenger_count` 1-10, `pickup_hour` 0-23, `pickup_dayofweek` 0-6, `pickup_month` 1-12, `pickup_weekday` 0 or 1; `total_fare` strictly between 0 and 5000. No value may be missing. Infinite values count as missing.
- An invalid row is never dropped silently: it is quarantined with a `reason` of the form `<column>: <check>` (several reasons joined by `; `).
- If more than 20% of the rows are quarantined (strictly more), preparation fails with a `ValueError`. Exactly 20% is accepted.
- If fewer than 100 valid rows remain, preparation fails with a `ValueError`. Exactly 100 is accepted.
- Both limits come from `config/monitoring.yml` (`validation.max_invalid_share`, `validation.min_valid_rows`).

### 2.3 Ingestion

- `month` must be 1 to 12 and `limit` at least 100, otherwise `ValueError`.
- Ingesting the same source twice (same URL and limit) does not duplicate rows in `training_trips` or `quarantine_trips`.

## 3. Drift detection (`services/pipeline/taxi_drift.py`)

- For each feature, the PSI compares the current data with the reference data:
  - a feature with at most `categorical_max_unique` (20) distinct values in the reference is compared category by category, over the union of the categories of both samples;
  - otherwise the reference is cut into `psi_bins` (10) quantile bins whose outer edges are open;
  - shares are floored at 0.0001 before computing `Σ (current − reference) × ln(current / reference)`.
- The PSI of two identical samples is 0.
- A feature drifts when its PSI is at least `psi_threshold` (0.2) **or** its KS statistic is at least `ks_statistic_threshold` (0.2).
- The dataset drifts when the share of drifted features is at least `dataset_share_threshold` (0.3).
- All thresholds are read from `config/monitoring.yml` (path overridable with `MONITORING_CONFIG`); none is hard-coded.
- When no champion exists yet, the run is a baseline: no drift, share 0.

### 3.1 Simulated drift

The drift scenario shifts only the data compared with the reference, never the training data: `pu_location_id` + 100 (capped at 265), `pickup_hour` + 8 modulo 24, `passenger_count` + 2 (capped at 6).

## 4. Training and promotion (`services/pipeline/flow.py`)

- The candidate and the current champion are scored on the same validation split (RMSE).
- The candidate is promoted to `champion` if there is no champion or if its RMSE is strictly lower. A tie keeps the champion.
- The alias moves only after the model, the drift summary, the reference data and its SHA-256 tag are stored.
- Each run tags `promoted_to_champion` (`True` or `False`).

## 5. Alerting (`services/prometheus/alert_rules.yml`, `services/alertmanager/alertmanager.yml`)

Every alert has a `for:` duration, a `severity` label (`page` or `ticket`), a `layer` label, and the annotations `summary`, `description`, `action` and `runbook_url`.

| Alert | Fires when | For | Severity |
| --- | --- | --- | --- |
| `HighErrorRate` | 5xx share of API responses > 5% and traffic > 0.2 req/s (1 m rate) | 30 s | page |
| `HighLatencyP99` | p99 of `/fare_predict` duration > 1 s (1 m rate) | 30 s | ticket |
| `ServiceDown` | a scrape target is down (`up == 0`) | 15 s | page |
| `ModelNotLoaded` | `model_loaded == 0` or the gauge is absent | 1 m | page |
| `DataDriftDetected` | `data_drift_detected == 1` | 15 s | ticket |
| `OnlineModelErrorHigh` | online RMSE (2 m rate) > 1.25 × validation RMSE | 30 s | ticket |
| `ModelPerformanceDegraded` | candidate RMSE > 1.2 × champion RMSE | 1 m | ticket |
| `BusinessThroughputLow` | fewer than 30 successful predictions per minute (absent series counts as 0) | 30 s | ticket |

While `ServiceDown` fires for `prediction_api`, the notifications of `ModelNotLoaded` and `BusinessThroughputLow` are inhibited; the alerts still fire in Prometheus.

## 6. Supporting services

- **Alert receiver** (`services/alert_webhook`): `POST /alerts` stores each alert of an Alertmanager payload, newest first, keeping at most 200; `GET /alerts` lists them; `DELETE /alerts` clears them.
- **Controller** (`services/controller`): can only stop or start `prediction_api`. Another service returns 403, another action 400, a missing container 404, a Docker error 502.
- **Load simulator** (`services/load_simulator`): `PUT /settings` accepts `running`, `requests_per_second` (0.2 to 20), `error_rate` (0 to 1) and optional `label_bias` (-0.9 to 3). `GET /status` returns the counters `sent`, `succeeded`, `rejected` (422) and `failed`.
- **Portal** (`services/frontend`): Streamlit operations portal. It requires a password (`PORTAL_PASSWORD`) and refuses access when none is configured.

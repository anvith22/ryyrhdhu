"""Integration tests for FastAPI endpoints using TestClient."""

from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_api_health_endpoint():
    """Verify /api/health returns system status and ingested database coverage."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "healthy"
    assert "actuals" in data
    assert "forecasts" in data
    assert data["actuals"]["count"] > 0
    assert data["forecasts"]["count"] > 0
    assert "assumptions" in data
    assert "UTC" in data["assumptions"]["timezone"]


def test_api_compare_endpoint():
    """Verify /api/compare returns 24 hourly settlement slots, summary metrics, and publish run bounds."""
    response = client.get("/api/compare", params={"delivery_date": "2026-01-15", "cutoff_hour": 9})
    assert response.status_code == 200
    data = response.json()

    assert data["delivery_date"] == "2026-01-15"
    assert data["cutoff_hour_utc"] == 9
    assert len(data["slots"]) == 24
    assert "summary" in data
    assert data["summary"]["total_slots"] == 24
    assert data["summary"]["forecasted_slots"] == 24
    assert data["summary"]["coverage"] == 1.0
    assert "mae" in data["summary"]
    assert "assumptions" in data
    assert "forecast_run_publish_time_min" in data
    assert "forecast_run_publish_time_max" in data


def test_api_metrics_endpoint():
    """Verify /api/metrics aggregates accuracy over a date range at hourly resolution with signed quantiles."""
    response = client.get(
        "/api/metrics",
        params={"start": "2026-01-01", "end": "2026-01-07", "cutoff_hour": 9},
    )
    assert response.status_code == 200
    data = response.json()

    assert data["start_date"] == "2026-01-01"
    assert data["end_date"] == "2026-01-07"
    assert data["n_total_slots"] == 7 * 24
    assert data["n_forecasted_slots"] == 7 * 24
    assert data["coverage"] == 1.0
    assert data["mae"] is not None
    assert data["rmse"] is not None
    assert data["bias"] is not None
    assert "p10" in data
    assert "p90" in data
    assert "normalized_mae" in data


def test_api_metrics_by_cutoff_endpoint():
    """Verify /api/metrics/by-cutoff returns metrics across cutoffs 0..23."""
    response = client.get("/api/metrics/by-cutoff", params={"start": "2026-01-01", "end": "2026-01-07"})
    assert response.status_code == 200
    data = response.json()

    assert len(data["by_cutoff"]) == 24
    assert data["by_cutoff"][9]["cutoff_hour_utc"] == 9
    assert data["by_cutoff"][9]["mae"] is not None
    assert "common_mae" in data["by_cutoff"][9]
    assert data["n_common_hours"] is not None


def test_api_metrics_daily_endpoint():
    """Verify /api/metrics/daily returns daily metrics breakdown."""
    response = client.get(
        "/api/metrics/daily",
        params={"start": "2026-01-01", "end": "2026-01-07", "cutoff_hour": 9},
    )
    assert response.status_code == 200
    data = response.json()

    assert len(data["daily"]) == 7
    assert data["daily"][0]["delivery_date"] == "2026-01-01"
    assert data["daily"][0]["mean_actual_mw"] is not None


def test_api_error_distribution_endpoint():
    """Verify /api/error-distribution returns histogram bins."""
    response = client.get(
        "/api/error-distribution",
        params={"start": "2026-01-01", "end": "2026-01-07", "cutoff_hour": 9},
    )
    assert response.status_code == 200
    data = response.json()

    assert data["total_count"] > 0
    assert len(data["bins"]) > 0
    assert "bin_label" in data["bins"][0]


def test_api_cutoff_hour_validation():
    """Verify that an invalid cutoff_hour (< 0 or > 23) returns HTTP 422 validation error."""
    response = client.get("/api/compare", params={"delivery_date": "2026-01-15", "cutoff_hour": 25})
    assert response.status_code == 422


def test_api_out_of_bounds_date_validation():
    """Verify that dates outside the snapshot bounds return HTTP 400."""
    response = client.get("/api/actuals", params={"start": "2020-01-01", "end": "2020-01-05"})
    assert response.status_code == 400
    assert "outside available snapshot bounds" in response.json()["detail"]

import pandas as pd
import requests

B = "https://data.elexon.co.uk/bmrs/api/v1/datasets"

def get(name, params):
    r = requests.get(f"{B}/{name}/stream", params=params, timeout=120)
    r.raise_for_status()
    j = r.json()
    return pd.DataFrame(j["data"] if isinstance(j, dict) and "data" in j else j)

# Actuals: wind only, half-hourly -> hourly mean
a = get("FUELHH", {"settlementDateFrom": "2026-01-01", "settlementDateTo": "2026-01-31"})
a = a[a.fuelType == "WIND"].copy()
a["startTime"] = pd.to_datetime(a.startTime, utc=True)
act = a.groupby(a.startTime.dt.floor("h")).generation.mean()

# Forecasts: all runs published from 30 Dec to 31 Jan
f = get("WINDFOR", {"publishDateTimeFrom": "2025-12-30T00:00Z",
                    "publishDateTimeTo": "2026-01-31T23:59Z"})
f["startTime"] = pd.to_datetime(f.startTime, utc=True)
f["publishTime"] = pd.to_datetime(f.publishTime, utc=True)

# For each delivery day D: latest forecast per hour with publishTime <= D-1 09:00 UTC
rows = []
for d in pd.date_range("2026-01-01", "2026-01-31", tz="UTC"):
    cut = d - pd.Timedelta(days=1) + pd.Timedelta(hours=9)
    s = f[(f.startTime >= d) & (f.startTime < d + pd.Timedelta(days=1)) & (f.publishTime <= cut)]
    rows.append(s.sort_values("publishTime").groupby("startTime").tail(1))
s = pd.concat(rows).set_index("startTime")

e = (s.generation - act.reindex(s.index)).dropna()   # forecast - actual
print("hours:", len(e))
print("MAE:", round(e.abs().mean(), 2))
print("bias:", round(e.mean(), 2))
print("RMSE:", round((e**2).mean() ** 0.5, 2))
print("P90 abs error:", round(e.abs().quantile(0.9), 2))

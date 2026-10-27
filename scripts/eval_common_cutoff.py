from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# Ensure repository root is on sys.path for direct script execution
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.forecast_service import compare  # noqa: E402

start_date = date(2026, 1, 1)
end_date = date(2026, 1, 31)

cutoff_dfs = {}
for h in range(24):
    curr = start_date
    rows = []
    while curr <= end_date:
        res = compare(curr, cutoff_hour_utc=h)
        for s in res['slots']:
            rows.append({
                'start_time': s['start_time'],
                'forecast_mw': s['forecast_mw'],
                'actual_mw': s['actual_mw'],
                'error_mw': s['error_mw']
            })
        curr += timedelta(days=1)
    df = pd.DataFrame(rows)
    cutoff_dfs[h] = df

common_mask = pd.Series(True, index=cutoff_dfs[0].index)
for h in range(24):
    common_mask = common_mask & cutoff_dfs[h]['forecast_mw'].notna()

print(f"Common mask count: {common_mask.sum()}")

for h in [0, 9, 22, 23]:
    df_c = cutoff_dfs[h][common_mask]
    mae = df_c['error_mw'].abs().mean()
    rmse = np.sqrt((df_c['error_mw']**2).mean())
    bias = df_c['error_mw'].mean()
    p90 = df_c['error_mw'].abs().quantile(0.9)
    print(f"Cutoff {h:2d} COMMON SET (n={len(df_c)}): MAE={mae:.2f}, RMSE={rmse:.2f}, Bias={bias:.2f}, P90={p90:.2f}")
    df_own = cutoff_dfs[h].dropna(subset=['error_mw'])
    own_mae = df_own['error_mw'].abs().mean()
    own_bias = df_own['error_mw'].mean()
    print(f"Cutoff {h:2d} OWN SET    (n={len(df_own)}): MAE={own_mae:.2f}, Bias={own_bias:.2f}")

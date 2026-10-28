# UK Wind Generation Forecast Platform: Technical Lead Review & Defense Guide

> **Purpose:** A complete, comprehensive defense guide containing 15 rigorous technical lead review questions spanning **Architecture**, **Correctness**, **Data Modeling & Assumptions**, **Statistical Rigor**, and **Deployment & Scalability**.  
> **How to Use This Document:** Each question includes:
> 1. **Why the Tech Lead Asks This** (the underlying risk or concept being tested).
> 2. **Common Junior Pitfalls** (what sounds naive, incomplete, or wrong).
> 3. **The Senior Model Answer** (authoritative, code-accurate, commercially grounded).

---

## Table of Contents
1. [Core Correctness & Look-Ahead Bias](#1-core-correctness--look-ahead-bias)
   - [Question 1: Look-Ahead Bias Prevention in Cutoff Selection](#question-1-look-ahead-bias-prevention-in-cutoff-selection)
   - [Question 2: Real Database Run Selection & Horizon Evaluation](#question-2-real-database-run-selection--horizon-evaluation)
   - [Question 3: Error Sign Convention & Cash-Out Asymmetry](#question-3-error-sign-convention--cash-out-asymmetry)
2. [Data Modeling & Market Assumptions](#2-data-modeling--market-assumptions)
   - [Question 4: The +1,852 MW Persistent Positive Bias](#question-4-the-1852-mw-persistent-positive-bias)
   - [Question 5: Early Cutoff Coverage Drop (682 vs 744 Hours)](#question-5-early-cutoff-coverage-drop-682-vs-744-hours)
   - [Question 6: Hourly Resolution Alignment vs Interpolation](#question-6-hourly-resolution-alignment-vs-interpolation)
3. [Architecture & Database Design](#3-architecture--database-design)
   - [Question 7: SQLite Snapshot vs Live Relational Database](#question-7-sqlite-snapshot-vs-live-relational-database)
   - [Question 8: SQL Window Functions vs Self-Joins](#question-8-sql-window-functions-vs-self-joins)
   - [Question 9: Dynamic Cutoff Parameter & Sensitivity Curve](#question-9-dynamic-cutoff-parameter--sensitivity-curve)
4. [Statistical Rigor & Metric Formulation](#4-statistical-rigor--metric-formulation)
   - [Question 10: Normalized MAE vs Percentage Error (MAPE)](#question-10-normalized-mae-vs-percentage-error-mape)
   - [Question 11: Python/NumPy Metrics vs Pure SQL Aggregation](#question-11-pythonnumpy-metrics-vs-pure-sql-aggregation)
   - [Question 12: Mathematical Derivation of P10–P90 Risk Band](#question-12-mathematical-derivation-of-p10p90-risk-band)
5. [Testing, Deployment & Production Scalability](#5-testing-deployment--production-scalability)
   - [Question 13: Test Coverage, Fixtures & Regression Prevention](#question-13-test-coverage-fixtures--regression-prevention)
   - [Question 14: Multi-Stage Dockerfile, Security & SPA Fallback](#question-14-multi-stage-dockerfile-security--spa-fallback)
   - [Question 15: Production Evolution: Streaming & Pan-European Scale](#question-15-production-evolution-streaming--pan-european-scale)

---

# 1. Core Correctness & Look-Ahead Bias

---

### Question 1: Look-Ahead Bias Prevention in Cutoff Selection
> **Tech Lead:** *"In energy trading backtests, look-ahead bias is fatal—if we accidentally leak future weather runs into historical decision points, our model looks artificially brilliant until we trade real capital and lose money.*  
> *Walk me through how `select_latest_forecasts()` guarantees that zero future data leaks into the day-ahead procurement decision. Specifically: for a target delivery hour on day $D$, what exact timestamp represents the decision cutoff, which forecast runs in the database are eligible, and how does the SQL query select the winning forecast?"*

#### Why the Tech Lead Asks This:
They want to know if you truly understand timestamp arithmetic and market deadlines, or if you simply wrote an unconstrained query that grabs the best or latest available forecast regardless of when it arrived.

#### Common Junior Pitfalls:
* Saying "it just selects the latest forecast in the database" without mentioning the cutoff condition.
* Confusing delivery day $D$ with trading day $D-1$.
* Not knowing the exact SQL mechanism used to filter candidates.

#### Senior Model Answer:
"Our system prevents look-ahead bias by enforcing a strict chronological decision cutoff before querying forecasts:
1. **Cutoff Timestamp Construction:** In `backend/app/services/forecast_service.py`, for any target delivery day $D$ and cutoff hour $H$ (default 09:00 UTC), the cutoff is defined as:
   $$\text{Cutoff} = (D - 1\text{ day}) \text{ at } H\text{:00:00 UTC}$$
   For delivery day `2026-01-15` and cutoff 9, the exact cutoff string is `'2026-01-14T09:00:00Z'`.
2. **Eligibility Rule:** A forecast row in `forecasts_wind` is eligible if and only if its `publish_time <= '2026-01-14T09:00:00Z'`. Any forecast published at `09:05` or `12:00` UTC on $D-1$, or on day $D$ itself, is strictly discarded.
3. **SQL Selection via CTE & Window Function:**
   ```sql
   WITH ranked AS (
       SELECT start_time, publish_time, generation_mw, horizon_hours,
              ROW_NUMBER() OVER (
                  PARTITION BY start_time
                  ORDER BY publish_time DESC
              ) as rn
       FROM forecasts_wind
       WHERE start_time >= :day_start
         AND start_time <= :day_end
         AND publish_time <= :cutoff_str
   )
   SELECT start_time, publish_time, generation_mw, horizon_hours
   FROM ranked
   WHERE rn = 1;
   ```
   The CTE groups all eligible historical runs for each delivery slot by `PARTITION BY start_time`, sorts them newest-first by `ORDER BY publish_time DESC`, and `WHERE rn = 1` extracts the single latest forecast that existed when the trader had to click 'submit'."

---

### Question 2: Real Database Run Selection & Horizon Evaluation
> **Tech Lead:** *"Let's test your understanding with real data. In our SQLite snapshot for delivery slot `2026-01-15T12:00:00Z`, 24 distinct forecast runs exist. Why was the `2026-01-14T07:30:00Z` run selected, why was the `09:30 UTC` run rejected even though it was closer in time, and why do some rows have negative horizons?"*

#### Why the Tech Lead Asks This:
They are testing whether you have actually inspected the underlying raw data or are just reciting documentation theory.

#### Common Junior Pitfalls:
* Not knowing that National Grid publishes multiple forecast updates per day.
* Assuming the latest published run before delivery is always used.
* Being unable to explain what a negative horizon means.

#### Senior Model Answer:
"For target hour `2026-01-15T12:00:00Z`:
1. **The Selected Run:** At our decision deadline of $D-1$ 09:00 UTC (`2026-01-14T09:00:00Z`), the latest forecast National Grid had published was the **`2026-01-14T07:30:00Z`** run, predicting **11,049.0 MW** with a horizon of **28.5 hours** ($12:00 - 07:30$).
2. **Why 09:30 UTC was Rejected:** The next update arrived at `2026-01-14T09:30:00Z` (predicting 11,178.0 MW, horizon 26.5h). Even though it was closer to delivery, it arrived 30 minutes *after* our 09:00 trading cutoff. Selecting it would be look-ahead bias—simulating a trade with information we did not possess at bid submission time.
3. **Negative Horizons:** In raw WINDFOR data, approximately 20% of records have `publish_time > start_time`. For example, a record with start time `12:00` and publish time `12:25` has a horizon of $-0.42\text{ hours}$. These are National Grid retrospective backcasts or outturn adjustments. Our ingestion cleaner logs them, and `metrics_by_horizon()` explicitly filters them out (`WHERE horizon_hours > 0`) so they never contaminate forward predictive evaluations."

---

### Question 3: Error Sign Convention & Cash-Out Asymmetry
> **Tech Lead:** *"In your services and schemas, you define `error = forecast - actual`. Why did you pick that direction instead of `actual - forecast`, and what is the commercial financial asymmetry between a positive error and a negative error on a UK trading desk?"*

#### Why the Tech Lead Asks This:
Sign conventions are notoriously mixed across data science and trading desks. A tech lead wants to ensure your metrics map directly to P&L and imbalance settlement mechanics.

#### Common Junior Pitfalls:
* Saying "it doesn't matter as long as we take absolute value."
* Confusing a 'short' position with a 'long' position.
* Failing to explain cash-out settlement (System Buy vs System Sell Prices).

#### Senior Model Answer:
"We strictly adhere to the wholesale power market convention:

$$\text{Error} = \text{Forecast} - \text{Actual}$$

This sign convention directly maps to our imbalance position:
* **Over-Forecast ($\text{Error} > 0$):**
  * The trading desk expected high wind generation.
  * Because Net Demand is $\text{Customer Load} - \text{Wind}$, expecting more wind led the desk to purchase **less** wholesale power on day-ahead auctions.
  * In real time, the wind failed to materialize. The desk's physical supply is less than its customer demand, leaving the desk in a **short position**.
  * **Commercial Consequence:** The desk is exposed to the Balancing Mechanism and must purchase emergency replacement energy from NESO at **System Buy Price (cash-out buy)**. During low-wind periods across Great Britain, System Buy Prices can spike from £70/MWh to over £500/MWh or even £2,000/MWh!
* **Under-Forecast ($\text{Error} < 0$):**
  * The desk expected low wind, over-procured day-ahead power, and physical wind surged.
  * Real-time status: **Long position**.
  * **Commercial Consequence:** The desk must spill or sell its excess power to NESO at **System Sell Price (cash-out sell)**, which can drop to £0/MWh or even turn negative, forcing the generator to pay to dispose of surplus energy."

---

# 2. Data Modeling & Market Assumptions

---

### Question 4: The +1,852 MW Persistent Positive Bias
> **Tech Lead:** *"When looking at the monthly metrics for January 2026 at the 09:00 UTC cutoff, your system reports a massive positive bias of +1,852 MW and an MAE of 2,142 MW. Did your pipeline introduce an offset bug, and if not, why didn't you just subtract 1,852 MW from every forecast to make your model look better?"*

#### Why the Tech Lead Asks This:
This tests intellectual honesty. Many junior data scientists try to 'fix' dataset discrepancies by applying synthetic calibration constants without understanding the underlying physical data generation process.

#### Common Junior Pitfalls:
* Panicking and claiming there might be a bug in the code.
* Recommending a hardcoded offset adjustment like `forecast = forecast - 1852`.
* Not knowing what Elexon's `FUELHH` and `WINDFOR` streams actually measure.

#### Senior Model Answer:
"The +1,852 MW bias is not a bug; it is an inherent physical and regulatory property of the public Elexon datasets:
1. **Scope Difference:**
   * **`FUELHH` (Actuals):** Covers only transmission-connected Balancing Mechanism Units (BMUs) with operational metering. Elexon’s official documentation explicitly warns: *'Renewable generation figures can be underestimated because the dataset excludes embedded generation and wind farms that lack operational meters.'*
   * **`WINDFOR` (Forecasts):** National Grid ESO models total wind generation across the entirety of Great Britain, including embedded wind connected to local distribution networks (DNOs).
2. **Why We Do NOT Subtract 1,852 MW:**
   * We evaluated the daily ratio of forecast to actual across all 31 days in January 2026. The ratio ranges from **0.89 to 1.93** with a median of **1.14**.
   * It is not a fixed scalar constant or simple additive offset. The variance is driven by both weather forecasting error and fluctuating embedded generation output.
   * Applying a synthetic static offset would be intellectually dishonest—it would fake accuracy on an uncalibrated baseline. Instead, we document this caveat prominently in `ASSUMPTIONS_META`, display it in the methodology modal, and evaluate the numbers as measured."

---

### Question 5: Early Cutoff Coverage Drop (682 vs 744 Hours)
> **Tech Lead:** *"In `metrics_by_cutoff()`, cutoffs at 00:00, 01:00, and 02:00 UTC report 682 hours of coverage instead of 744 hours (91.7%). Why did this happen? Did your ingestion script fail to fetch data for late December or early January?"*

#### Why the Tech Lead Asks This:
They want to see if you can trace an apparent data anomaly down to the exact data producer payload specifications.

#### Common Junior Pitfalls:
* Blaming the database ingestion script or API rate limiting.
* Guessing that wind was calm on those days so no forecast was generated.
* Not knowing how far ahead National Grid forecast runs project.

#### Senior Model Answer:
"This is caused by the forward horizon reach of National Grid's forecast publication cycle:
1. **The 46.5-Hour Forward Limit:** For delivery on day $D$, a cutoff of D-1 00:00 UTC selects the latest run published before midnight, which is strictly the **(D-2) 22:30 UTC run**. National Grid's forecast payload contains 73 hourly steps extending to $+46.5\text{ hours}$ ahead.
2. **The Reach Gap:** Exactly 46.5 hours after D-2 22:30 UTC is **delivery day $D$ at 21:00 UTC**.
3. **The Missing Hours:** Delivery slots 22:00 and 23:00 UTC fall beyond the forward reach of that forecast run. They remain unforecasted until the D-1 02:30 UTC run arrives.
4. **The Math:** In a 31-day month, exactly 2 hours per day lack an eligible forecast before 00:00 UTC:
   $$31 \text{ days} \times 2 \text{ hours} = 62 \text{ unforecasted hours}$$
   $$744 \text{ total hours} - 62 = \mathbf{682 \text{ hours}}$$
5. **Our Solution:** Rather than hiding or interpolating those hours, `metrics_by_cutoff()` calculates **both** the like-for-like common set ($n=682$) and the per-cutoff own-coverage set ($n=744$), giving traders visibility into both pure accuracy and liquidity/coverage risk."

---

### Question 6: Hourly Resolution Alignment vs Interpolation
> **Tech Lead:** *"FUELHH actuals are reported in 30-minute settlement periods, but WINDFOR forecasts are hourly. Why did you downsample actuals to 1 hour instead of interpolating forecasts up to 30 minutes?"*

#### Why the Tech Lead Asks This:
They want to see how you handle frequency mismatches in time-series data without introducing mathematical artifacts.

#### Common Junior Pitfalls:
* Saying "it was easier to code."
* Suggesting cubic spline interpolation without realizing it invents non-existent meteorological forecasts.
* Forgetting that raw 30-minute actuals are still needed for charting.

#### Senior Model Answer:
"We deliberately average pairs of 30-minute actuals into 1-hour blocks for evaluation:
$$\text{Actual}_{\text{hourly}}(T) = \frac{\text{Actual}(T) + \text{Actual}(T + 30\text{m})}{2}$$
* **Why Not Interpolate Forecasts:** National Grid only publishes 1-hour forecasts. If we used linear, cubic spline, or nearest-neighbor interpolation to create 30-minute forecast points, we would be inventing synthetic data that National Grid never forecasted. That creates artificial precision and distorts error metrics.
* **Preserving Chart Detail:** In `backend/app/api/routes.py`, we expose raw half-hourly actuals via `/api/actuals`. In `frontend/src/components/DecisionView.tsx`, the chart plots all 48 half-hour actual points against the 24 stepped hourly forecast points. Traders get maximum visual resolution without compromising evaluation integrity."

---

# 3. Architecture & Database Design

---

### Question 7: SQLite Snapshot vs Live Relational Database
> **Tech Lead:** *"You chose an embedded SQLite file (`data/wind_energy.db`) rather than running a managed PostgreSQL or DuckDB instance. Defend that architectural choice, explain what SQLite pragmas you enabled, and tell me when this design breaks."*

#### Why the Tech Lead Asks This:
They want to know if you can evaluate architectural trade-offs based on operational constraints rather than just picking tools because they are popular.

#### Common Junior Pitfalls:
* Apologizing for using SQLite as if it's toy technology.
* Not knowing about SQLite URI read-only modes (`mode=ro`).
* Having no concrete migration plan for production scale.

#### Senior Model Answer:
"We chose SQLite because it perfectly satisfies the platform's requirements with zero operational complexity:
1. **Zero Infrastructure Overhead:** SQLite is built into Python's standard library. It requires no background database daemon, zero network TCP hops, and zero connection pool management.
2. **Sub-Millisecond Relational Performance:** With indexed compound lookups (`idx_forecasts_compound` on `start_time, publish_time`), analytical queries execute in under 2 milliseconds.
3. **Concurrency & Read-Only Safety:** In `backend/app/ingest/storage.py::get_sqlite_connection()`, we connect using `file:{path}?mode=ro`. This allows multiple Uvicorn worker threads to execute concurrent analytical reads without write lock contention, and runs cleanly on read-only container filesystems.
4. **When It Breaks:** This design breaks when we transition from a deterministic backtesting snapshot to a real-time live ingestion platform receiving streaming updates from multiple power exchanges. At that point, concurrent writes would bottleneck SQLite.
5. **Scale Path:** For a live production environment, we would migrate time-series storage to **TimescaleDB** or **ClickHouse** with Redis caching for hot day-ahead queries."

---

### Question 8: SQL Window Functions vs Self-Joins
> **Tech Lead:** *"In `select_latest_forecasts()`, you use a Common Table Expression with `ROW_NUMBER() OVER (PARTITION BY start_time ORDER BY publish_time DESC)`. Why use a window function instead of a simpler `GROUP BY start_time` with `MAX(publish_time)`?"*

#### Why the Tech Lead Asks This:
This tests your SQL expertise and understanding of query planner execution.

#### Common Junior Pitfalls:
* Believing `GROUP BY start_time` can return non-aggregated columns like `generation_mw` and `horizon_hours` safely in standard SQL.
* Thinking window functions are always slower than self-joins.

#### Senior Model Answer:
"In standard SQL, if you write:
```sql
SELECT start_time, MAX(publish_time), generation_mw
FROM forecasts_wind
GROUP BY start_time;
```
That query is invalid in PostgreSQL and undefined in SQLite (unless `generation_mw` is functionally dependent). `MAX(publish_time)` finds the highest timestamp, but the engine cannot guarantee that `generation_mw` and `horizon_hours` in the returned row belong to that same maximum record.

To solve that without window functions, you must write a self-join:
```sql
SELECT f.* FROM forecasts_wind f
INNER JOIN (
    SELECT start_time, MAX(publish_time) AS max_pub
    FROM forecasts_wind WHERE publish_time <= :cutoff GROUP BY start_time
) latest ON f.start_time = latest.start_time AND f.publish_time = latest.max_pub;
```
That requires two passes over the table: one to aggregate and another to join.  
Our window function `ROW_NUMBER() OVER (PARTITION BY start_time ORDER BY publish_time DESC)` executes in a single streaming pass using our compound index `idx_forecasts_compound (start_time, publish_time)`. Filtering `WHERE rn = 1` extracts the exact scalar values associated with that latest run cleanly and deterministically."

---

### Question 9: Dynamic Cutoff Parameter & Sensitivity Curve
> **Tech Lead:** *"Your API allows passing `cutoff_hour` as a query parameter (0..23). What did your sensitivity analysis reveal about forecast accuracy between 00:00 and 09:00 UTC, and does allowing dynamic cutoffs cause a performance problem?"*

#### Why the Tech Lead Asks This:
They want to know if the analytical capability of the platform translates into actionable commercial insights, and how dynamic parameters affect computational load.

#### Common Junior Pitfalls:
* Reciting raw numbers without explaining commercial impact.
* Not knowing how long dynamic cutoff calculations take.

#### Senior Model Answer:
"The dynamic cutoff parameter powers our Decision Timing Sensitivity analysis:
1. **The Commercial Finding:** Evaluating the like-for-like common set (682 hours in January 2026):
   * At **00:00 UTC** cutoff, MAE is **2,216.16 MW**.
   * At **09:00 UTC** (assumed auction commitment cutoff), MAE drops to **2,157.04 MW** (a 59.12 MW or 2.7% error reduction).
   * Beyond gate closure, delaying to **23:00 UTC** further reduces MAE to **1,931.48 MW** (a further 225.56 MW or 10.5% reduction).
   * **Takeaway:** Within the actionable morning window before auction close, forecast gains are modest (2.7%). Major forecast improvements occur later in the afternoon when real-time meteorological observations update. Traders should not take excessive liquidity risk delaying bids early in the morning.
2. **Performance:** Because our database is an indexed 5.8 MB SQLite snapshot, computing a full day's comparison for any cutoff takes **1.2 milliseconds**. For multi-year production backtests, we would pre-materialize daily cutoff aggregates into rollup tables during nightly ETL batches."

---

# 4. Statistical Rigor & Metric Formulation

---

### Question 10: Normalized MAE vs Percentage Error (MAPE)
> **Tech Lead:** *"Standard business dashboards love Mean Absolute Percentage Error (MAPE). Why did you exclude MAPE from your platform, and how is Normalized MAE formulated?"*

#### Why the Tech Lead Asks This:
In renewable energy, MAPE is notorious for producing absurd results. Asking this separates novice statisticians from experienced energy analysts.

#### Common Junior Pitfalls:
* Recommending standard MAPE ($\frac{|\text{Error}|}{\text{Actual}}$).
* Suggesting adding an arbitrary epsilon like $+0.001$ to prevent division by zero.
* Not knowing what happens to wind generation on calm days.

#### Senior Model Answer:
"We explicitly excluded MAPE because of the **zero-denominator instability**:
$$\text{MAPE} = \frac{1}{N} \sum_{i=1}^N \frac{|\text{Forecast}_i - \text{Actual}_i|}{\text{Actual}_i}$$
During anticyclonic (high-pressure) winter weather in Great Britain, national wind generation can drop below 100 MW or near 0 MW. If actual wind is 10 MW and the forecast was 60 MW, the absolute error is only 50 MW (insignificant for the national grid), but MAPE reports:
$$\frac{|60 - 10|}{10} = 5.0 = \mathbf{500\% \text{ error!}}$$
A single calm afternoon would completely corrupt the monthly metric, making it statistically meaningless.

Instead, we use **Normalized MAE (NMAE)**:
$$\text{NMAE} = \frac{\text{MAE}}{\overline{\text{Actual}}} = \frac{\frac{1}{N} \sum |\text{Error}_i|}{\frac{1}{N} \sum \text{Actual}_i}$$
By scaling total absolute error against the monthly mean actual generation ($11,580.74\text{ MW}$ in January), the denominator is stable and non-zero, giving a reliable relative error metric of **18.5%**."

---

### Question 11: Python/NumPy Metrics vs Pure SQL Aggregation
> **Tech Lead:** *"In `forecast_service.py`, you extract rows into Python lists and compute MAE, RMSE, and bias using NumPy. Why do that in application memory rather than using SQL aggregation functions like `AVG(ABS(forecast - actual))`?"*

#### Why the Tech Lead Asks This:
They want to know where you draw the line between database responsibility and application server responsibility.

#### Common Junior Pitfalls:
* Claiming SQL cannot calculate averages or absolute values.
* Ignoring database engine limitations.
* Forgetting about percentiles.

#### Senior Model Answer:
"We perform metric calculations in Python/NumPy for two architectural reasons:
1. **SQLite Engine Limitations:** Standard SQLite does not include built-in functions for percentiles ($q_{10}, q_{50}, q_{90}$), and standard deviation/square root requires loading extension libraries. Our platform needs exact quantile error estimates for the P10–P90 risk corridor.
2. **Frequency Alignment Logic:** In our workflow, 30-minute actuals must first be averaged into hourly buckets before joining with forecasts. Doing multi-step CTE window joins, half-hourly aggregations, and quantile calculations entirely in SQLite SQL would result in brittle, difficult-to-maintain SQL.
3. **Memory Footprint:** For an entire month, the dataset is only 744 hourly error floats. Loading 744 numbers into a NumPy array takes microseconds and less than 10 KB of RAM. NumPy executes `np.mean()`, `np.sqrt()`, and `np.percentile()` in sub-millisecond C-optimized vector routines."

---

### Question 12: Mathematical Derivation of P10–P90 Risk Band
> **Tech Lead:** *"In the frontend chart, you display an empirical plausible actual generation band around the forecast. Walk me through the exact math: why do you subtract $q_{90}$ to find the lower bound, and why do you clamp at zero?"*

#### Why the Tech Lead Asks This:
This tests whether you understand the inverse relationship between forecast errors and physical outturns.

#### Common Junior Pitfalls:
* Saying "lower bound is forecast minus $q_{10}$ and upper bound is forecast plus $q_{90}$."
* Forgetting that error was defined as $\text{Forecast} - \text{Actual}$.
* Allowing negative generation values on the chart.

#### Senior Model Answer:
"Our error convention is:
$$\text{Error} = \text{Forecast} - \text{Actual} \iff \text{Actual} = \text{Forecast} - \text{Error}$$
Notice the minus sign! When error is high (at its 90th percentile, meaning the forecast was an extreme over-prediction), the actual generation is at its **lowest**. When error is low (at its 10th percentile), actual generation is at its **highest**.

Therefore:
$$\text{Plausible Lower Bound} = \max(0, \text{Forecast} - q_{90})$$
$$\text{Plausible Upper Bound} = \max(0, \text{Forecast} - q_{10})$$

In January 2026 across all 744 hours at cutoff 9:
* $q_{10} = -549.30\text{ MW}$
* $q_{90} = +4,300.15\text{ MW}$

If tomorrow's forecast is **10,000 MW**:
* $\text{Lower Bound} = \max(0, 10,000 - 4,300.15) = \mathbf{5,699.85\text{ MW}}$
* $\text{Upper Bound} = \max(0, 10,000 - (-549.30)) = \mathbf{10,549.30\text{ MW}}$

We apply $\max(0, \dots)$ in `frontend/src/utils/calculations.ts` because physical wind turbines cannot generate negative power; unclamped bands would produce nonsensical negative megawatts on the chart."

---

# 5. Testing, Deployment & Production Scalability

---

### Question 13: Test Coverage, Fixtures & Regression Prevention
> **Tech Lead:** *"How do you know this system doesn't break when someone changes a SQL query or updates a dependency? What tests exist, what edge cases do they cover, and how are they run?"*

#### Why the Tech Lead Asks This:
They want to know if you take software engineering rigor seriously or if you rely on manual clicking in the UI.

#### Common Junior Pitfalls:
* Saying "I clicked through the UI and it worked."
* Not knowing which test frameworks are configured.
* Failing to mention CI automation.

#### Senior Model Answer:
"We maintain automated test suites across both backend and frontend, integrated into GitHub Actions CI:
1. **Backend Tests (Pytest, 18 automated tests):**
   * [backend/tests/test_api.py](file:///c:/Users/Admin/Desktop/energy_/backend/tests/test_api.py): Tests all HTTP endpoints, verifies response models, and asserts that out-of-bounds dates (e.g. `2024-01-01` or `2027-01-01`) return HTTP 400 with descriptive error payloads.
   * [backend/tests/test_cleaner.py](file:///c:/Users/Admin/Desktop/energy_/backend/tests/test_cleaner.py): Tests timestamp parsing, type coercion, deduplication of duplicate primary keys `(start_time, publish_time)`, and missing 30-min settlement slot detection.
   * [backend/tests/test_services.py](file:///c:/Users/Admin/Desktop/energy_/backend/tests/test_services.py): Uses SQLite in-memory fixtures to verify cutoff selection logic, mathematical MAE/RMSE/bias formulas, and hourly aggregation.
2. **Frontend Tests (Vitest, 4 tests):**
   * [frontend/src/tests/calculations.test.ts](file:///c:/Users/Admin/Desktop/energy_/frontend/src/tests/calculations.test.ts): Tests `calculatePlausibleBand()` for clamping at 0 MW, handling null/undefined inputs, and computing stacked area height.
3. **Continuous Integration (`.github/workflows/ci.yml`):**
   * On every push and pull request, GitHub Actions runs Ruff linting, Pytest, Vitest, Vite production bundling, and a Docker build smoke test."

---

### Question 14: Multi-Stage Dockerfile, Security & SPA Fallback
> **Tech Lead:** *"Walk me through your `Dockerfile`. Why is it multi-stage, what user executes the process, how does container health checking work, and how does FastAPI serve React routes without 404ing?"*

#### Why the Tech Lead Asks This:
This tests your production readiness, container security awareness, and full-stack operational deployment knowledge.

#### Common Junior Pitfalls:
* Running containers as `root`.
* Shipping Node.js and build tools into the production runtime image.
* Not knowing how client-side SPA routing works on reload.

#### Senior Model Answer:
"Our container architecture follows cloud-native best practices:
1. **Multi-Stage Build:**
   * **Stage 1 (`node:20.18-alpine`):** Copies `package.json`, runs `npm ci`, and compiles the React application into static production assets (`frontend/dist`).
   * **Stage 2 (`python:3.11-slim`):** Production runtime. Copies only the compiled static assets from Stage 1 into `/app/frontend/dist`. Node.js, npm, and build caches are completely discarded, resulting in a minimal, secure image.
2. **Security & Non-Root Execution:**
   * Line 30 creates a system user: `groupadd -r appuser && useradd -r -g appuser appuser`.
   * The container drops root privileges via `USER appuser`, preventing container breakout vulnerabilities.
3. **Health Checking:**
   * Lines 53–54 implement a zero-dependency health check using Python standard library `urllib.request` testing `http://127.0.0.1:$PORT/api/health` every 30 seconds.
4. **SPA Fallback Routing:**
   * In [backend/app/main.py](file:///c:/Users/Admin/Desktop/energy_/backend/app/main.py), we mount `/assets` statically and implement a catch-all route `/{full_path:path}`. If a requested file exists, it is served; otherwise, it returns `frontend/dist/index.html`. This ensures that refreshing the browser on `/accuracy` or `/horizon` routes never results in an HTTP 404."

---

### Question 15: Production Evolution: Streaming & Pan-European Scale
> **Tech Lead:** *"Imagine this platform is funded for enterprise deployment: we need to evaluate 5 years of historical wind and solar data across 15 European bidding zones (Germany, France, Nordics, UK), with live streaming data updating every 15 minutes. How does your architecture change?"*

#### Why the Tech Lead Asks This:
This is the ultimate senior engineer question: can you see beyond your current prototype and design an enterprise-grade distributed system?

#### Common Junior Pitfalls:
* Saying "we just need a bigger SQLite file and a bigger EC2 instance."
* Suggesting rebuilding the entire database on every request.
* Having no concept of streaming ETL, distributed storage, or CDN caching.

#### Senior Model Answer:
"To scale to enterprise pan-European production, we would evolve the architecture into three decoupled layers:
1. **Streaming Ingestion Layer:**
   * Replace batch CLI scripts with distributed asynchronous workers using **Temporal** or **Celery + Redis**.
   * Workers consume live API feeds from Elexon BMRS, ENTSO-E Transparency Platform, and commercial weather APIs (StormGeo, Meteologica), publishing clean events to an **Apache Kafka** or **AWS Kinesis** event bus.
2. **Distributed Analytical Storage Layer:**
   * Migrate from SQLite to **TimescaleDB** (PostgreSQL-native) or **ClickHouse**.
   * Use hypertables partitioned by `(market_zone, start_time)` with columnar compression. 5 years of 15-minute data across 15 zones is ~25 million rows—ClickHouse can scan and aggregate that volume in under 50 milliseconds.
3. **Decoupled Edge Frontend & API Gateway:**
   * Host the React SPA on an edge CDN (**AWS CloudFront** / **Cloudflare Pages**).
   * Deploy the FastAPI analytics engine as containerized microservices on **AWS ECS Fargate** or **Kubernetes (EKS)** behind an API Gateway with horizontal auto-scaling.
4. **Pre-Materialization & Caching:**
   * Because historical delivery days are immutable, run nightly rollup batches to pre-calculate daily error distributions and cutoff sensitivity tables into a **Redis** cache. Analytical read queries would achieve sub-5ms response times globally."

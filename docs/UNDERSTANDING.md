# UK Wind Generation Forecast & Evaluation Platform: Engineering & Business Architecture Guide

> **Audience:** Junior Software Engineer / Energy Quant preparing for a technical lead presentation.  
> **Author:** Senior Energy & Software Systems Engineer.  
> **Tone & Objective:** Patient, rigorous, and completely accurate to the code. This guide walks you through every layer of the system—from commercial power market incentives down to database queries and React component renders—so you can present this project to your technical lead with absolute confidence.

---

## Table of Contents
1. [The Business Problem in Plain English](#1-the-business-problem-in-plain-english)
2. [End-to-End Request Walkthrough (Trace of a Single Request)](#2-end-to-end-request-walkthrough)
3. [File-by-File Repository Guide](#3-file-by-file-repository-guide)
4. [Core Logic & Worked Numeric Example (From Real Database Data)](#4-core-logic--worked-numeric-example)
5. [Evaluation Metrics: Formulas, Code Locations & Hand Calculations](#5-evaluation-metrics-formulas-code-locations--hand-calculations)
6. [Design Decisions, Trade-Offs & Scalability](#6-design-decisions-trade-offs--scalability)
7. [Known Limitations & Technical Assumptions](#7-known-limitations--technical-assumptions)
8. [Glossary of Energy Market & Technical Terms](#8-glossary)
9. [Senior Engineer Coaching: How to Defend This in Your Tech Lead Review](#9-senior-engineer-coaching-how-to-defend-this-in-your-tech-lead-review)

---

## 1. The Business Problem in Plain English

### The Great Britain Day-Ahead Electricity Market
In the UK power grid, electricity cannot be stored at grid scale cheaply. Large batteries and pumped storage exist, but they cover only a tiny fraction of national demand. As a result, the national grid operator (National Energy System Operator, or **NESO**, formerly National Grid ESO) must maintain grid frequency at exactly **50.0 Hz** every second. If supply drops below demand, frequency drops, triggering blackouts. If supply exceeds demand, frequency spikes, damaging physical transmission infrastructure.

Electricity suppliers (retail utility companies like Octopus, British Gas, E.ON) sell electricity to homes, factories, and businesses. Because customer consumption is determined by human behavior (turning on kettles, heaters, machines), the supplier cannot change customer demand in real time. Instead, the supplier must purchase wholesale electricity in advance to match what their customers will consume tomorrow (**Day $D$**).

This forward purchasing happens predominantly in the **Day-Ahead Wholesale Auctions** (such as EPEX SPOT and Nord Pool) on day **$D-1$** (the day before physical delivery).

### Why Wind Generation Changes Everything
Wind turbines generate power whenever the wind blows. Their fuel is wind, which is free. This means wind power has an effective short-run marginal operating cost of near **£0/MWh**. When wind is blowing strongly across the British Isles, wind power floods the grid, displacing expensive, gas-fired Combined Cycle Gas Turbines (CCGT) that burn costly natural gas.

Energy traders and commercial desk dispatchers track **Net Demand**:

$$\text{Net Demand} = \text{System Demand (Customer Load)} - \text{Wind Generation}$$

Because wholesale power is purchased to cover Net Demand:
- When a trading desk expects **high wind generation**, they purchase **less** wholesale power in the day-ahead auction.
- When a trading desk expects **low wind generation**, they purchase **more** wholesale power in the day-ahead auction.

### The Asymmetric Commercial Cost of Forecast Error
On day $D-1$ around **09:00 UTC** (the internal risk commitment cutoff simulated by our platform), commercial desks must lock in their bidding volumes for physical delivery on day $D$ (15 to 39 hours ahead). But weather forecasts are imperfect. 

What happens when the wind forecast deviates from reality?

```
                     ┌────────────────────────────────────────────────────────┐
                     │          Day-Ahead Wind Forecast Error                 │
                     │            Error = Forecast - Actual                   │
                     └───────────────────┬────────────────────────────────────┘
                                         │
               ┌─────────────────────────┴─────────────────────────┐
               ▼                                                   ▼
     ┌──────────────────────────────────┐        ┌──────────────────────────────────┐
     │    Over-Forecast (Error > 0)     │        │    Under-Forecast (Error < 0)    │
     │        Forecast > Actual         │        │        Forecast < Actual         │
     ├──────────────────────────────────┤        ├──────────────────────────────────┤
     │ • Desk expected more wind power. │        │ • Desk expected less wind power. │
     │ • Desk purchased LESS wholesale  │        │ • Desk purchased MORE wholesale  │
     │   power on the day-ahead market. │        │   power on the day-ahead market. │
     │ • Physical reality: wind drops.  │        │ • Physical reality: wind surges. │
     │ • Real-time status: SHORT        │        │ • Real-time status: LONG         │
     │ • Penalty: Desk must buy missing │        │ • Penalty: Desk has surplus      │
     │   power in the real-time         │        │   unneeded power; must spill or  │
     │   Balancing Mechanism (BM) at    │        │   sell it at low System Sell     │
     │   penal System Buy Prices!       │        │   Prices (cash-out discount).    │
     └──────────────────────────────────┘        └──────────────────────────────────┘
```

A **short position** caused by over-forecasting is particularly dangerous. When total grid wind unexpectedly collapses, the entire system is strained, gas peakers are fired up, and real-time System Buy Prices can spike from £70/MWh to over £500/MWh or even £2,000/MWh!

### The Problem This Platform Solves
Traders cannot afford to treat forecasts as a black-box single number. They need an engineering platform that answers three mission-critical operational questions:
1. **Decision Integrity:** Exactly what forecast was published *before* our 09:00 UTC trading cutoff? (We must never cheat by looking at forecasts published at 10:00 or 15:00 UTC on D-1, which would introduce look-ahead bias).
2. **Empirical Risk Banding:** Given historical error patterns, what is the realistic P10–P90 safety corridor for physical delivery?
3. **Decision Timing Sensitivity:** If we delay committing our bids from 00:00 to 09:00 UTC (or beyond), how much does forecast error actually drop? Is the accuracy gain worth the auction liquidity risk?

---

## 2. End-to-End Request Walkthrough

Let us trace a single, concrete user action from click to canvas: the user opens the web application, selects delivery date **`2026-01-15`**, keeps the default cutoff at **`09:00 UTC`**, and the comparison chart renders.

```
[Browser / UI] 
      │ 
      │ 1. User picks '2026-01-15' & '09:00 UTC'
      ▼
[React Component: frontend/src/components/DecisionView.tsx]
      │
      │ 2. useEffect() triggers apiClient calls
      ▼
[HTTP Client: frontend/src/api/client.ts]
      │
      │ 3. fetchJson('/api/compare?delivery_date=2026-01-15&cutoff_hour=9')
      ▼
[Vite Dev Server (Port 5173)] ──(Reverse Proxy /api/*)──► [FastAPI Backend (Port 8000)]
                                                                  │
      ┌───────────────────────────────────────────────────────────┘
      │
      ├──> backend/app/main.py (CORS + routing to api_router)
      │      ▼
      ├──> backend/app/api/routes.py::get_compare_route()
      │      │  • Validates delivery_date and cutoff_hour
      │      │  • Checks bounds via _validate_date_in_range()
      │      ▼
      ├──> backend/app/services/forecast_service.py::compare()
      │      │
      │      ├── 1. select_latest_forecasts(delivery_date, cutoff_hour_utc)
      │      │      ├── get_sqlite_connection(read_only=True)
      │      │      └── SQL Query 1: CTE with ROW_NUMBER() OVER (...) filtering publish_time <= cutoff
      │      │
      │      ├── 2. get_hourly_actuals_map(delivery_date, delivery_date)
      │      │      ├── get_actuals(delivery_date, delivery_date)
      │      │      ├── SQL Query 2: SELECT from actuals_wind for 48 half-hour settlement periods
      │      │      └── Aggregates pairs of 30-min actuals into 24 hourly arithmetic means
      │      │
      │      ├── 3. Computes hourly errors (error = forecast - actual) and day summary stats
      │      ▼
      ├──> Pydantic Serialization: backend/app/api/schemas.py::CompareResponse
      │      ▼
      └──> HTTP 200 JSON Response delivered to Browser
             │
             ▼
[React UI: frontend/src/components/DecisionView.tsx]
      │
      ├──> useMemo() aligns 48 half-hourly actuals with 24 hourly forecasts
      ├──> frontend/src/utils/calculations.ts::calculatePlausibleBand() (computes lower/upper bounds)
      └──> Recharts <ResponsiveContainer> renders <ComposedChart> with actuals, forecast, and P10-P90 band
```

### Step 1: User Action in React
* **File:** [frontend/src/components/DecisionView.tsx](file:///c:/Users/Admin/Desktop/energy_/frontend/src/components/DecisionView.tsx)
* **Trigger:** The user changes the date input `<input type="date">` to `2026-01-15` and cutoff dropdown `<select>` to `9`.
* **State Change:** `deliveryDate` is updated to `"2026-01-15"`, `cutoffHour` is updated to `9`.
* **Hook Execution:** `useEffect` fires in `DecisionView.tsx`:
  ```typescript
  Promise.all([
    apiClient.getCompare(deliveryDate, cutoffHour),
    apiClient.getActuals(deliveryDate, deliveryDate),
    apiClient.getMetrics('2026-01-01', '2026-01-31', cutoffHour),
  ])
  ```

### Step 2: HTTP Client Request
* **File:** [frontend/src/api/client.ts](file:///c:/Users/Admin/Desktop/energy_/frontend/src/api/client.ts)
* **Function:** `apiClient.getCompare(deliveryDate, cutoffHour)`
* **Network Call:** Calls `fetchJson<CompareResponse>('/api/compare?delivery_date=2026-01-15&cutoff_hour=9')`.
* **Network Routing:**
  - In development: `frontend/vite.config.ts` intercepts `/api` and proxies to `http://localhost:8000`.
  - In Docker/Production: `backend/app/main.py` serves the SPA via `serve_spa()` fallback and `/api` endpoints directly on the same port.

### Step 3: Backend Application & Route Handling
* **File:** [backend/app/main.py](file:///c:/Users/Admin/Desktop/energy_/backend/app/main.py)
* **Processing:** Passes request through `CORSMiddleware` and matches prefix `/api` into `api_router`.
* **File:** [backend/app/api/routes.py](file:///c:/Users/Admin/Desktop/energy_/backend/app/api/routes.py)
* **Function:** `get_compare_route(delivery_date: date, cutoff_hour: int = 9)`
* **Validation:**
  - `delivery_date` is parsed as an ISO `datetime.date`.
  - `cutoff_hour` is checked against `Query(ge=0, le=23)`.
  - Calls `_validate_date_in_range(delivery_date, bounds, "delivery_date")`. It queries `get_data_coverage_bounds()` to confirm `2026-01-15` falls within `2025-12-30` to `2026-02-03`.
  - Calls `compare(delivery_date=delivery_date, cutoff_hour_utc=cutoff_hour)`.

### Step 4: Core Domain Execution & Database Queries
* **File:** [backend/app/services/forecast_service.py](file:///c:/Users/Admin/Desktop/energy_/backend/app/services/forecast_service.py)
* **Function:** `compare(delivery_date: date, cutoff_hour_utc: int = 9)`

#### 4a. Calculating Cutoff Timestamp
```python
cutoff_dt = datetime.combine(delivery_date - timedelta(days=1), time(cutoff_hour_utc, 0), tzinfo=timezone.utc)
cutoff_str = cutoff_dt.strftime("%Y-%m-%dT%H:%M:%SZ")  # "2026-01-14T09:00:00Z"
```

#### 4b. Selecting Decision Forecasts (Query 1)
Calls `select_latest_forecasts(delivery_date, cutoff_hour_utc)`. It opens a read-only SQLite connection (`mode=ro`) via `storage.py::get_sqlite_connection()` and executes:
```sql
WITH ranked AS (
    SELECT
        start_time,
        publish_time,
        generation_mw,
        horizon_hours,
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
* **Why this query is crucial:** For each delivery hour between `2026-01-15T00:00:00Z` and `2026-01-15T23:00:00Z`, multiple forecast runs exist. The CTE partitions by `start_time`, orders candidate runs by `publish_time DESC`, and `rn = 1` picks the latest run published *before or at* `2026-01-14T09:00:00Z`.
* The function aligns this into all 24 slots using `generate_day_hourly_slots(delivery_date)`. Any hour lacking an eligible forecast is preserved as `None` (unforecasted), never interpolated.

#### 4c. Fetching and Aggregating Actuals (Query 2)
Calls `get_hourly_actuals_map(delivery_date, delivery_date)` which calls `get_actuals()`:
```sql
SELECT start_time, generation_mw, settlement_date, settlement_period
FROM actuals_wind
WHERE start_time >= :day_start AND start_time <= :day_end
ORDER BY start_time ASC;
```
* Returns 48 rows (one per 30-minute settlement period).
* `get_hourly_actuals_map()` floors timestamps to the top of the hour and takes the arithmetic mean of the two half-hours:
  $$\text{Actual}_{\text{hourly}}(12:00) = \frac{\text{Actual}(12:00) + \text{Actual}(12:30)}{2}$$

#### 4d. Hourly Joining & Metrics
In `compare()`:
* Iterates through the 24 slots.
* For each slot, computes:
  $$\text{Error} = \text{Forecast} - \text{Actual}$$
  $$\text{Absolute Error} = |\text{Error}|$$
* Calculates day summary metrics:
  - `coverage = forecasted_slots / total_slots` ($24 / 24 = 1.0$)
  - `mae = np.mean(abs_errors)`
  - `rmse = np.sqrt(np.mean(np.square(errors)))`
  - `bias = np.mean(errors)`

### Step 5: Serialization
* **File:** [backend/app/api/schemas.py](file:///c:/Users/Admin/Desktop/energy_/backend/app/api/schemas.py)
* Pydantic model `CompareResponse` validates types, formats numbers, and returns HTTP 200 with JSON payload containing `delivery_date`, `cutoff_time`, `summary`, and `slots`.

### Step 6: Frontend Rendering
* **File:** [frontend/src/components/DecisionView.tsx](file:///c:/Users/Admin/Desktop/energy_/frontend/src/components/DecisionView.tsx)
* Retrieves `p10` (-549.3 MW) and `p90` (+4,300.2 MW) from the concurrent `getMetrics()` response.
* In `useMemo()`, combines the 48 half-hourly actual records with the 24 hourly forecast records.
* For each point, calls `calculatePlausibleBand(forecastMw, q10, q90)` from [frontend/src/utils/calculations.ts](file:///c:/Users/Admin/Desktop/energy_/frontend/src/utils/calculations.ts):
  ```typescript
  const rawLower = forecastMw - q90;
  const rawUpper = forecastMw - q10;
  const lower = Math.max(0, Math.round(rawLower * 10) / 10);
  const upper = Math.max(0, Math.round(rawUpper * 10) / 10);
  const bandHeight = Math.max(0, Math.round((upper - lower) * 10) / 10);
  ```
* Feeds `chartData` into Recharts `<ResponsiveContainer>` `<ComposedChart>`:
  - `<Area dataKey="plausible_lower" fill="transparent" stackId="band" />` (invisible base)
  - `<Area dataKey="plausible_band" fill="rgba(16, 185, 129, 0.15)" stroke="none" stackId="band" />` (stacked translucent green corridor)
  - `<Line dataKey="actual_mw_30m" stroke="var(--accent-emerald)" strokeWidth={2} dot={false} />` (solid emerald actuals line)
  - `<Line dataKey="forecast_mw" stroke="var(--accent-cyan)" strokeDasharray="5 5" strokeWidth={2} />` (dashed cyan decision forecast line)
* Renders the top KPI banner (`MAE`, `Bias`, `P10–P90 Spread`, `Cutoff Lead Time`) and the expandable 24-hour audit table.

---

## 3. File-by-File Repository Guide

Here is an architectural map of every file in the repository, explaining what it does, why it exists, and what would fail if it were deleted.

### Backend Architecture (`backend/`)

#### `backend/app/main.py`
* **What it does:** Instantiates the FastAPI application, attaches CORS middleware, includes API routes, and configures SPA static file serving with fallback to `frontend/dist/index.html`.
* **Why it exists:** Provides the central HTTP entrypoint for both local development and containerized production execution.
* **What breaks without it:** The backend web server cannot boot; all API requests fail; Docker container health checks fail.

#### `backend/app/api/routes.py`
* **What it does:** Defines REST API endpoints (`/api/health`, `/api/actuals`, `/api/forecast/latest`, `/api/compare`, `/api/metrics`, `/api/metrics/by-cutoff`, `/api/metrics/daily`, `/api/error-distribution`, `/api/metrics/by-horizon`, `/api/metrics/by-hour`).
* **Why it exists:** Translates HTTP queries, validates date ranges against database coverage, and delegates business logic to service functions.
* **What breaks without it:** The frontend has no API endpoints to query; all client data fetching returns 404 Not Found.

#### `backend/app/api/schemas.py`
* **What it does:** Declares Pydantic v2 data models for request validation and response serialization (`CompareResponse`, `MetricsResponse`, `HealthResponse`, etc.).
* **Why it exists:** Enforces schema contracts, prevents type errors from escaping to clients, and generates automated OpenAPI docs at `/docs`.
* **What breaks without it:** FastAPI cannot serialize responses or validate incoming data types; OpenAPI documentation breaks.

#### `backend/app/services/forecast_service.py`
* **What it does:** Contains all power market business logic: cutoff timestamp filtering, hourly actual aggregation, signed and absolute error calculation, MAE/RMSE/bias/quantile math, and horizon degradation bucketing.
* **Why it exists:** Keeps mathematical and domain logic isolated from web transport and HTTP routing.
* **What breaks without it:** No comparisons, backtests, or metric evaluations can be performed.

#### `backend/app/ingest/storage.py`
* **What it does:** Manages SQLite database connection lifecycles (`get_sqlite_connection`), schema creation with indexes (`init_db`), and batch writes (`save_actuals`, `save_forecasts`).
* **Why it exists:** Encapsulates persistence logic and enforces read-only mode (`mode=ro`) for safe container execution.
* **What breaks without it:** Neither ingestion scripts nor the API can read or write to `data/wind_energy.db`.

#### `backend/app/ingest/cleaner.py`
* **What it does:** Validates and cleans raw API records: parses UTC timestamps, coerces generation to float, deduplicates primary keys, computes forecast horizons (`(startTime - publishTime)` in hours), and flags missing 30-min settlement periods.
* **Why it exists:** Protects downstream analytics from dirty external data, duplicate payloads, or timestamp anomalies.
* **What breaks without it:** Ingestion of raw Elexon payloads causes database primary key collisions, type errors, and flawed time-series analysis.

#### `backend/app/ingest/client.py`
* **What it does:** HTTP client for Elexon BMRS API streams (`FUELHH` and `WINDFOR`). Implements date-chunking, request timeouts, and exponential backoff retry logic for HTTP 429/5xx errors.
* **Why it exists:** Provides a robust network layer that handles rate-limiting and large data volume paging from UK grid APIs.
* **What breaks without it:** Fresh data cannot be fetched from Elexon BMRS.

#### `backend/app/ingest/pipeline.py`
* **What it does:** Orchestrates the ingestion workflow: calls `client.py` to fetch, `cleaner.py` to clean, and `storage.py` to persist.
* **Why it exists:** Coordinates multi-step ETL runs with unified logging and error reporting.
* **What breaks without it:** Ingestion scripts must manually coordinate clients, cleaners, and databases.

#### `backend/tests/test_api.py`, `test_cleaner.py`, `test_services.py`
* **What they do:** Pytest test suite covering route integration, date validation, deduplication, cutoff selection, and metric formulas.
* **Why they exist:** Ensures regression testing in CI and verifies that core logic adheres to specification.
* **What breaks without them:** Regressions in mathematical formulas or database queries go undetected.

#### `backend/requirements.txt`
* **What it does:** Lists Python package dependencies (`fastapi`, `uvicorn`, `pydantic`, `pandas`, `numpy`, `requests`, `pytest`, `ruff`).
* **Why it exists:** Pins production runtime dependencies for pip and Docker builds.
* **What breaks without it:** Container and CI builds fail due to missing dependencies.

---

### Frontend Architecture (`frontend/`)

#### `frontend/src/App.tsx`
* **What it does:** Top-level React component. Manages global state for view switching (`decision` | `accuracy` | `horizon`), selected dates, and the methodology modal.
* **Why it exists:** Provides single-page application state coordination.
* **What breaks without it:** React cannot render the application.

#### `frontend/src/main.tsx` & `frontend/index.html`
* **What they do:** Entry point that mounts React into the DOM element `#root` and loads Google Fonts (Inter, JetBrains Mono).
* **Why they exist:** Web browser entry point.
* **What breaks without it:** The browser loads a blank page.

#### `frontend/src/index.css`
* **What it does:** Implements the complete design system: custom CSS properties (dark slate `#0a0e17`, cyan `#06b6d4`, emerald `#10b981`, amber `#f59e0b`), typography, utility classes, and glassmorphic card layouts.
* **Why it exists:** Provides a unified, high-contrast trading terminal aesthetic without Tailwind dependencies.
* **What breaks without it:** Application renders unstyled HTML.

#### `frontend/src/components/DecisionView.tsx`
* **What it does:** Primary trader dashboard. Renders the Day-Ahead Decision View: Recharts composed graph (30-min actuals, hourly decision forecast, P10–P90 plausible band), KPI cards, and expandable 24-hour audit table.
* **Why it exists:** Directly addresses the power trader's core workflow: locking in day-ahead volume bids before the cutoff deadline.
* **What breaks without it:** The primary decision-support screen is missing.

#### `frontend/src/components/AccuracyDashboard.tsx`
* **What it does:** Historical backtest dashboard. Visualizes overall MAE/RMSE/bias KPIs, daily actual vs forecast trends, signed error distribution histogram (500 MW bins), and diurnal (hour-of-day) bias profiles.
* **Why it exists:** Enables quantitative validation of model bias and accuracy over multi-week delivery periods.
* **What breaks without it:** Analysts cannot evaluate historical forecast reliability or diurnal patterns.

#### `frontend/src/components/HorizonTimingView.tsx`
* **What it does:** Visualizes forecast degradation by lead time (0-6h, 6-12h, ..., 48h+) and a 24-hour decision timing sensitivity curve (evaluating accuracy gains from delaying decisions).
* **Why it exists:** Answers the operational timing question: "Is it commercially worth delaying our procurement commitments?"
* **What breaks without it:** Traders have no visibility into lead-time degradation or cutoff timing value.

#### `frontend/src/components/MethodologyModal.tsx`
* **What it does:** Slide-out modal detailing data definitions, Elexon BMU metered scope caveats, cutoff rules, and the error sign convention.
* **Why it exists:** Ensures full commercial and mathematical transparency without cluttering operational charts.
* **What breaks without it:** Non-expert users may misinterpret the persistent positive bias or sign conventions.

#### `frontend/src/components/Navbar.tsx`
* **What it does:** Renders header branding, system status badge, view switcher navigation, and the methodology modal trigger.
* **Why it exists:** Provides global header navigation.
* **What breaks without it:** Users cannot navigate between dashboard views.

#### `frontend/src/api/client.ts` & `frontend/src/types/api.ts`
* **What they do:** Type-safe HTTP client wrapper around `fetch()` and TypeScript interfaces mirroring backend Pydantic models.
* **Why it exists:** Guarantees compile-time type safety across the network boundary.
* **What breaks without them:** Components must execute untyped raw `fetch()` calls, risking runtime undefined property crashes.

#### `frontend/src/utils/calculations.ts` & `formatters.ts`
* **What they do:** Pure utility functions: `calculatePlausibleBand()` (computes lower/upper bounds clamped at 0 MW), `formatMW()`, `formatSignedMW()`, `formatTimeUTC()`, and CSV export.
* **Why it exists:** Reusable, unit-tested presentation and statistical math.
* **What breaks without them:** Number formatting breaks; negative power predictions appear on charts.

#### `frontend/src/tests/calculations.test.ts`
* **What it does:** Vitest unit test suite validating that `calculatePlausibleBand()` correctly handles clamping at 0 MW, null values, and stacked band height.
* **Why it exists:** Prevents mathematical regressions in frontend chart calculations.
* **What breaks without it:** Broken band calculations go unnoticed.

#### `frontend/vite.config.ts`, `package.json`, `tsconfig.json`
* **What they do:** Vite configuration, npm dependencies, and TypeScript compiler options.
* **Why they exist:** Coordinates frontend build, bundling, and type checking.
* **What breaks without them:** Frontend cannot be compiled or bundled.

---

### Data, Scripts & Infrastructure

#### `data/wind_energy.db`
* **What it does:** SQLite database containing 1,728 half-hourly actual records and 23,944 WINDFOR forecasts across the test window (30 Dec 2025 to 03 Feb 2026).
* **Why it exists:** Provides deterministic, offline data access with zero external API dependencies.
* **What breaks without it:** The backend has no data to query; all API endpoints return errors or empty results.

#### `scripts/run_ingest.py`
* **What it does:** CLI entry point to fetch fresh data from Elexon BMRS for any custom date window.
* **Why it exists:** Allows operators to refresh or extend the database snapshot without touching application code.
* **What breaks without it:** Ingestion must be manually triggered via python interactive shell.

#### `scripts/eval_common_cutoff.py`
* **What it does:** Computes the like-for-like sensitivity analysis across all 24 cutoffs on the common set of 682 delivery hours.
* **Why it exists:** Verifies the mathematical difference between common-set and own-coverage metrics.
* **What breaks without it:** Analysts cannot reproduce the like-for-like 682-hour benchmark figures cited in documentation.

#### `scripts/verify_metrics.py`
* **What it does:** Minimal verification script that queries Elexon directly, runs the hourly evaluation loop, and prints benchmark metrics.
* **Why it exists:** Provides an independent sanity check against production service logic.
* **What breaks without it:** Independent metric auditing requires re-writing ad-hoc scripts.

#### `scripts/build_notebook.py` & `notebooks/01_explore.ipynb`
* **What they do:** Programmatically compiles and runs an exploratory Jupyter notebook analyzing dataset dimensions, horizons, and distributions.
* **Why it exists:** Provides reproducible exploratory data analysis (EDA) for quantitative stakeholders.
* **What breaks without them:** Exploratory research is decoupled from codebase versions.

#### `Dockerfile` & `.dockerignore`
* **What it does:** Multi-stage production container build (Stage 1: Node 20 compiles Vite frontend; Stage 2: Python 3.11-slim runs Uvicorn as a non-root user `appuser` on `$PORT`).
* **Why it exists:** Packages the entire application and database into an immutable, self-contained deployment artifact.
* **What breaks without it:** Cannot run via Docker or deploy to container platforms (Heroku Container Stack, AWS ECS, Google Cloud Run).

#### `.github/workflows/ci.yml`
* **What it does:** Continuous Integration workflow executing Ruff linting, Pytest test suite, frontend Vitest tests, frontend Vite production build, and Docker build/smoke tests on every push.
* **Why it exists:** Prevents broken code, formatting violations, or failing containers from entering `main`.
* **What breaks without it:** Regressions are caught only after manual discovery.

#### `pyproject.toml`
* **What it does:** Configuration for Ruff linter/formatter and Pytest.
* **Why it exists:** Centralizes tool configurations in modern Python standards.
* **What breaks without it:** Tools fall back to defaults, causing inconsistent linting rules.

---

## 4. Core Logic & Worked Numeric Example

To master the core logic, let us walk through a **real delivery hour** directly from `data/wind_energy.db`.

### Delivery Target
* **Target Delivery Slot:** `2026-01-15T12:00:00Z` (12:00 to 13:00 UTC on January 15, 2026).
* **Market Decision Rule:** Day $D-1$ (`2026-01-14`) at **09:00:00 UTC** cutoff (`publish_time <= '2026-01-14T09:00:00Z'`).

### Step 1: Candidate Forecast Runs in SQLite
When we query `forecasts_wind` for `start_time = '2026-01-15T12:00:00Z'`, National Grid published 24 distinct forecast runs over time for this single hour:

| Publication Time (`publish_time`) | Forecast (`generation_mw`) | Horizon (`horizon_hours`) | Decision Status at D-1 09:00 UTC |
| :--- | :--- | :--- | :--- |
| `2026-01-13 02:30 UTC` | 11,938.0 MW | 57.5 h | Disqualified: superseded by newer eligible runs |
| `2026-01-13 04:30 UTC` | 11,888.0 MW | 55.5 h | Disqualified: superseded by newer eligible runs |
| `2026-01-13 07:30 UTC` | 11,562.0 MW | 52.5 h | Disqualified: superseded by newer eligible runs |
| `2026-01-13 09:30 UTC` | 11,749.0 MW | 50.5 h | Disqualified: superseded by newer eligible runs |
| `2026-01-13 11:30 UTC` | 11,400.0 MW | 48.5 h | Disqualified: superseded by newer eligible runs |
| `2026-01-13 15:30 UTC` | 11,025.0 MW | 44.5 h | Disqualified: superseded by newer eligible runs |
| `2026-01-13 18:30 UTC` | 11,075.0 MW | 41.5 h | Disqualified: superseded by newer eligible runs |
| `2026-01-13 22:30 UTC` | 11,080.0 MW | 37.5 h | Disqualified: superseded by newer eligible runs |
| `2026-01-14 02:30 UTC` | 11,049.0 MW | 33.5 h | Disqualified: superseded by newer eligible runs |
| `2026-01-14 04:30 UTC` | 11,049.0 MW | 31.5 h | Disqualified: superseded by newer eligible runs |
| **`2026-01-14 07:30 UTC`** | **11,049.0 MW** | **28.5 h** | **SELECTED: Latest published on or before D-1 09:00 UTC** |
| `2026-01-14 09:30 UTC` | 11,178.0 MW | 26.5 h | **REJECTED: Published after 09:00 cutoff (look-ahead bias)** |
| `2026-01-14 11:30 UTC` | 11,351.0 MW | 24.5 h | **REJECTED: Published after 09:00 cutoff (future information)** |
| `2026-01-14 15:30 UTC` | 11,854.0 MW | 20.5 h | **REJECTED: Published after 09:00 cutoff (future information)** |
| `2026-01-14 18:30 UTC` | 11,859.0 MW | 17.5 h | **REJECTED: Published after 09:00 cutoff (future information)** |
| `2026-01-14 22:30 UTC` | 11,155.0 MW | 13.5 h | **REJECTED: Published after 09:00 cutoff (future information)** |
| `2026-01-15 02:30 UTC` | 11,148.0 MW | 9.5 h | **REJECTED: Real-time day-of-delivery update** |
| `2026-01-15 04:30 UTC` | 10,693.0 MW | 7.5 h | **REJECTED: Real-time day-of-delivery update** |
| `2026-01-15 07:30 UTC` | 10,405.0 MW | 4.5 h | **REJECTED: Real-time day-of-delivery update** |
| `2026-01-15 09:30 UTC` | 10,503.0 MW | 2.5 h | **REJECTED: Real-time day-of-delivery update** |
| `2026-01-15 12:25 UTC` | 10,229.0 MW | -0.4 h | **REJECTED: Retrospective backcast (negative horizon)** |
| `2026-01-15 15:30 UTC` | 10,229.0 MW | -3.5 h | **REJECTED: Retrospective backcast (negative horizon)** |
| `2026-01-15 18:30 UTC` | 10,229.0 MW | -6.5 h | **REJECTED: Retrospective backcast (negative horizon)** |
| `2026-01-15 22:30 UTC` | 10,229.0 MW | -10.5 h | **REJECTED: Retrospective backcast (negative horizon)** |

#### Why `2026-01-14T07:30:00Z` Was Chosen:
At 09:00 UTC on day $D-1$, the 07:30 UTC run was the most up-to-date information in existence. The 09:30 UTC run did not arrive until 30 minutes *after* the auction bids were committed. Using it would be look-ahead bias (cheating with future data).

$$\text{Decision Forecast} = \mathbf{11,049.0\text{ MW}}$$

---

### Step 2: Hourly Actual Generation Outturn
Next, we retrieve the physical metered actuals from `actuals_wind` for the two half-hour settlement periods that make up the 12:00–13:00 UTC delivery hour:

| Settlement Period | Start Time (UTC) | Metered Wind (`generation_mw`) |
| :--- | :--- | :--- |
| Period 25 | `2026-01-15 12:00:00Z` | 9,742.0 MW |
| Period 26 | `2026-01-15 12:30:00Z` | 9,839.0 MW |

We align resolution by taking the arithmetic mean:
$$\text{Actual}_{\text{hourly}} = \frac{9,742.0 + 9,839.0}{2} = \mathbf{9,790.5\text{ MW}}$$

---

### Step 3: Error Calculation
Using the industry standard sign convention:
$$\text{Error} = \text{Forecast} - \text{Actual}$$
$$\text{Error} = 11,049.0 - 9,790.5 = \mathbf{+1,258.5\text{ MW}}$$
$$\text{Absolute Error} = |+1,258.5| = \mathbf{1,258.5\text{ MW}}$$

### Commercial Meaning:
1. The trading desk believed **11,049.0 MW** of wind power would be generated.
2. The desk purchased wholesale power under that expectation (purchasing less conventional power).
3. In real time, only **9,790.5 MW** arrived.
4. The desk was **short by 1,258.5 MW** during that hour. It was forced to buy balancing electricity from National Grid ESO at real-time cash-out buy prices.

---

## 5. Evaluation Metrics: Formulas, Code Locations & Hand Calculations

To verify that you understand the mathematical foundations, here is each metric used on the platform, where it is computed in the source code, and a simple 3-hour hand-calculation.

### Tiny 3-Hour Toy Example Dataset
Suppose our evaluation window consists of just 3 hours:
* **Hour 1:** $\text{Forecast} = 10,000\text{ MW}$, $\text{Actual} = 8,000\text{ MW} \implies \text{Error} = +2,000\text{ MW}, |\text{Error}| = 2,000\text{ MW}$
* **Hour 2:** $\text{Forecast} = 6,000\text{ MW}$, $\text{Actual} = 7,000\text{ MW} \implies \text{Error} = -1,000\text{ MW}, |\text{Error}| = 1,000\text{ MW}$
* **Hour 3:** $\text{Forecast} = 12,000\text{ MW}$, $\text{Actual} = 9,000\text{ MW} \implies \text{Error} = +3,000\text{ MW}, |\text{Error}| = 3,000\text{ MW}$

---

### 1. Mean Absolute Error (MAE)
* **What it measures:** The average magnitude of the forecast error, regardless of direction.
* **Mathematical Formula:**
  $$\text{MAE} = \frac{1}{N} \sum_{i=1}^N |\text{Forecast}_i - \text{Actual}_i| = \frac{1}{N} \sum_{i=1}^N |\text{Error}_i|$$
* **Code Location:** `backend/app/services/forecast_service.py`, inside `metrics()`, line 328:
  ```python
  mae = float(np.mean(all_abs_errors))
  ```
  *(Also in `compare()`, line 271: `round(float(np.mean(abs_errors)), 2)`)*
* **Hand Calculation:**
  $$\text{MAE} = \frac{|+2,000| + |-1,000| + |+3,000|}{3} = \frac{2,000 + 1,000 + 3,000}{3} = \frac{6,000}{3} = \mathbf{2,000\text{ MW}}$$

---

### 2. Root Mean Squared Error (RMSE)
* **What it measures:** The square root of the mean squared errors. Because errors are squared before averaging, RMSE heavily penalizes large ramp misses or extreme forecast blowouts.
* **Mathematical Formula:**
  $$\text{RMSE} = \sqrt{\frac{1}{N} \sum_{i=1}^N (\text{Forecast}_i - \text{Actual}_i)^2} = \sqrt{\frac{1}{N} \sum_{i=1}^N \text{Error}_i^2}$$
* **Code Location:** `backend/app/services/forecast_service.py`, inside `metrics()`, line 329:
  ```python
  rmse = float(np.sqrt(np.mean(np.square(all_errors))))
  ```
  *(Also in `compare()`, line 272: `round(float(np.sqrt(np.mean(np.square(errors)))), 2)`)*
* **Hand Calculation:**
  $$\text{Squared Errors} = [2,000^2, (-1,000)^2, 3,000^2] = [4,000,000, 1,000,000, 9,000,000]$$
  $$\text{Mean Squared Error} = \frac{4,000,000 + 1,000,000 + 9,000,000}{3} = \frac{14,000,000}{3} \approx 4,666,666.67$$
  $$\text{RMSE} = \sqrt{4,666,666.67} \approx \mathbf{2,160.25\text{ MW}}$$
  *(Note that $\text{RMSE} \ge \text{MAE}$; the 160.25 MW gap reflects the dispersion and variance in error sizes).*

---

### 3. Forecast Bias (Mean Signed Error)
* **What it measures:** The systematic tendency of the forecast to over-predict (positive bias) or under-predict (negative bias).
* **Mathematical Formula:**
  $$\text{Bias} = \frac{1}{N} \sum_{i=1}^N (\text{Forecast}_i - \text{Actual}_i) = \frac{1}{N} \sum_{i=1}^N \text{Error}_i$$
* **Code Location:** `backend/app/services/forecast_service.py`, inside `metrics()`, line 330:
  ```python
  bias = float(np.mean(all_errors))
  ```
  *(Also in `compare()`, line 273: `round(float(np.mean(errors)), 2)`)*
* **Hand Calculation:**
  $$\text{Bias} = \frac{(+2,000) + (-1,000) + (+3,000)}{3} = \frac{+4,000}{3} = \mathbf{+1,333.33\text{ MW}}$$
  *(Indicates a net systematic over-forecasting tendency of 1,333.33 MW).*

---

### 4. Normalized MAE (NMAE)
* **What it measures:** Relative forecast error scaled against mean generation.
* **Mathematical Formula:**
  $$\text{NMAE} = \frac{\text{MAE}}{\overline{\text{Actual}}} = \frac{\text{MAE}}{\frac{1}{N}\sum_{i=1}^N \text{Actual}_i}$$
* **Why not MAPE?** Standard Mean Absolute Percentage Error ($\frac{|\text{Error}|}{\text{Actual}}$) explodes to infinity whenever wind generation approaches 0 MW on calm days. Normalized MAE provides a stable denominator.
* **Code Location:** `backend/app/services/forecast_service.py`, inside `metrics()`, lines 344-345:
  ```python
  mean_actual = float(np.mean(all_actuals))
  norm_mae = float(mae / mean_actual) if mean_actual > 0 else None
  ```
* **Hand Calculation:**
  $$\overline{\text{Actual}} = \frac{8,000 + 7,000 + 9,000}{3} = \frac{24,000}{3} = 8,000\text{ MW}$$
  $$\text{NMAE} = \frac{2,000\text{ MW}}{8,000\text{ MW}} = \mathbf{0.25\text{ (or 25.0\%)}}$$

---

### 5. P90 Absolute Error
* **What it measures:** The 90th percentile of absolute error. In 90% of hours, the absolute forecast miss is less than or equal to this threshold.
* **Code Location:** `backend/app/services/forecast_service.py`, inside `metrics()`, line 334:
  ```python
  p90_abs = float(np.percentile(all_abs_errors, 90))
  ```
* **Hand Calculation:**
  For our sorted absolute errors $[1,000, 2,000, 3,000]$, the 90th percentile (via linear interpolation) represents the upper tail risk:
  $$\text{Index} = 0.90 \times (3 - 1) = 1.8 \implies 2,000 + 0.8 \times (3,000 - 2,000) = \mathbf{2,800\text{ MW}}$$

---

### 6. Coverage
* **What it measures:** The proportion of target delivery hours that had an eligible forecast published prior to the decision cutoff.
* **Mathematical Formula:**
  $$\text{Coverage} = \frac{N_{\text{forecasted}}}{N_{\text{total}}}$$
* **Code Location:** `backend/app/services/forecast_service.py`, inside `metrics()`, line 325:
  ```python
  coverage = round(n_forecasted / total_possible_hours, 4) if total_possible_hours > 0 else 0.0
  ```
  *(Also in `compare()`, line 270: `round(n_forecasted / total_hours, 4)`)*
* **Hand Calculation:**
  If 3 out of 3 hours had forecasts: $\text{Coverage} = 3 / 3 = \mathbf{1.0\text{ (100\%)}}$.

---

### 7. Empirical Signed Error Quantiles (P10 & P90 Banding)
* **What it measures:** The 10th and 90th percentiles of signed error ($\text{Forecast} - \text{Actual}$).
* **Code Location:** `backend/app/services/forecast_service.py`, lines 339, 341:
  ```python
  p10_signed = float(np.percentile(all_errors, 10))
  p90_signed = float(np.percentile(all_errors, 90))
  ```
* **How the Frontend Derives the Plausible Actual Band:**
  In [frontend/src/utils/calculations.ts](file:///c:/Users/Admin/Desktop/energy_/frontend/src/utils/calculations.ts):
  $$\text{Error} = \text{Forecast} - \text{Actual} \iff \text{Actual} = \text{Forecast} - \text{Error}$$
  Therefore:
  $$\text{Plausible Lower Bound} = \max(0, \text{Forecast} - q_{90})$$
  $$\text{Plausible Upper Bound} = \max(0, \text{Forecast} - q_{10})$$
  In January 2026 across all 744 hours at cutoff 9:
  $q_{10} = -549.3\text{ MW}$ and $q_{90} = +4,300.15\text{ MW}$.
  If tomorrow's forecast is $10,000\text{ MW}$:
  $$\text{Lower Bound} = \max(0, 10,000 - 4,300.15) = \mathbf{5,699.85\text{ MW}}$$
  $$\text{Upper Bound} = \max(0, 10,000 - (-549.3)) = \mathbf{10,549.30\text{ MW}}$$

---

## 6. Design Decisions, Trade-Offs & Scalability

When presenting to a technical lead, be prepared to explain **why** architectural decisions were made, their trade-offs, and how you would evolve them.

### 1. SQLite Snapshot vs. Live API Querying on Every Request
* **Decision:** Pre-populate an offline SQLite database (`data/wind_energy.db`) and query it locally.
* **Rationale:**
  - **Zero external network latency:** Sub-millisecond indexed relational queries versus 2–5 second external HTTP API round-trips.
  - **Deterministic evaluation:** Eliminates external API outages, rate limiting (HTTP 429), or historical data revisions during trading evaluations.
  - **Relational power:** Allows SQL `ROW_NUMBER() OVER (PARTITION BY start_time ORDER BY publish_time DESC)` to select the latest forecast before cutoff timestamps efficiently.
* **Trade-off:** Data is a historical snapshot; refreshing requires running `scripts/run_ingest.py`.
* **What to change at enterprise scale:**
  - In a live production trading room, deploy an asynchronous streaming ingestion worker (using Celery or Temporal) consuming real-time Elexon API feeds.
  - Store time-series in a distributed time-series or columnar database like **TimescaleDB** or **ClickHouse** with Redis caching for hot day-ahead queries.

---

### 2. Hourly Resolution Alignment vs. Interpolation
* **Decision:** Take the arithmetic mean of the two 30-minute FUELHH actuals to match WINDFOR's hourly publication timestamps.
* **Rationale:**
  - Avoids synthetic data fabrication: WINDFOR does not provide 30-minute resolution. Spline or linear interpolation would invent fake forecast precision that National Grid never published.
  - Preserves underlying raw 30-minute actuals in `/api/actuals` for high-resolution chart rendering.
* **Trade-off:** Evaluates 24 slots per day instead of 48 half-hour settlement periods.
* **What to change at enterprise scale:**
  - Procure specialized commercial weather vendor streams (e.g., Meteologica, ConWX, StormGeo) that natively deliver half-hourly forecasts matching UK settlement periods directly.

---

### 3. Dynamic Cutoff as a Query Parameter vs. Hardcoded 09:00 UTC
* **Decision:** Expose `cutoff_hour` (0..23) as an API query parameter across comparison, forecast, and metric endpoints.
* **Rationale:**
  - Enables decision timing sensitivity analysis: traders can directly measure how much accuracy improves if purchasing commitments are deferred from 00:00 UTC to 09:00 or 16:00 UTC.
* **Trade-off:** Requires on-the-fly SQL aggregation for any requested cutoff hour.
* **What to change at enterprise scale:**
  - For multi-year datasets spanning hundreds of cutoffs, pre-compute and materialize daily cutoff aggregates during nightly ETL batches into summary tables.

---

### 4. Single Multi-Stage Docker Container vs. Decoupled Microservices
* **Decision:** A multi-stage Dockerfile compiling the React Vite bundle into static assets and packaging it directly with FastAPI and Uvicorn.
* **Rationale:**
  - Zero deployment friction: single container image running as a secure non-root user (`appuser`) listening on `$PORT`, compatible with Heroku Container Stack, AWS ECS, Google Cloud Run, or local Docker.
  - Eliminates CORS issues in production: frontend and backend share the same origin and port.
* **Trade-off:** Frontend and backend scale together rather than independently.
* **What to change at enterprise scale:**
  - Decouple the React SPA to an edge CDN (AWS CloudFront / Cloudflare Pages) and run the FastAPI analytical backend as auto-scaling container services behind an API Gateway.

---

## 7. Known Limitations & Technical Assumptions

Honest engineering presentations state limitations clearly without guessing.

### 1. The Persistent Positive Bias Caveat (+1,852 MW)
* **Fact:** Across January 2026 at the 09:00 UTC cutoff, WINDFOR forecasts exceed FUELHH metered actuals by an average of **+1,852 MW** (MAE is 2,142 MW).
* **Underlying Cause:**
  - Elexon documentation explicitly confirms that `FUELHH` actuals cover only transmission-metered Balancing Mechanism Units (BMUs): *"Renewable generation figures can be underestimated because the dataset excludes embedded generation and wind farms that lack operational meters."*
  - Conversely, `WINDFOR` forecasts total generation across all Power Park Modules (PPMs) connected to the system.
* **Why we do NOT assume a constant offset:**
  - The ratio of daily forecast to actual varies between **0.89 and 1.93** (median **1.14**). It is not a fixed scalar constant. The data cannot separate atmospheric weather error from embedded generation scope differences. We document the caveat transparently and compute figures as measured.

---

### 2. Operational Gate Closure Assumption (`cutoff_hour = 9`)
* **Fact:** The platform configures `ASSUMED_GATE_CLOSURE_HOUR_UTC = 9`.
* **Caveat:** In the UK market, day-ahead power exchange auctions (EPEX SPOT and Nord Pool) run around 11:00–12:00 local time. The 09:00 UTC cutoff represents an assumed internal trading desk risk commitment deadline, not a statutory market gate closure.

---

### 3. Early Cutoff Coverage Drop (00:00–02:00 UTC)
* **Fact:** Decision cutoffs at 00:00, 01:00, and 02:00 UTC have **91.7% coverage** (682 out of 744 hours).
* **Reason:**
  - For delivery on day $D$, the D-1 00:00 UTC cutoff selects the latest run published before midnight, which is strictly the **(D-2) 22:30 UTC run**.
  - National Grid's 73-step forecast payload extends forward to +46.5 hours ahead.
  - Exactly 46.5 hours after D-2 22:30 UTC is **delivery day $D$ at 21:00 UTC**.
  - Delivery slots 22:00 and 23:00 UTC exceed the forward reach of that forecast run and remain unforecasted until the D-1 02:30 UTC run arrives.
  - Across 31 days in January, exactly 2 hours per day ($31 \times 2 = 62\text{ hours}$) lack a forecast ($744 - 62 = 682\text{ hours}$). The platform handles this by reporting both **common-set (n=682)** and **own-coverage (n=744)** metrics.

---

### 4. In-Sample P10–P90 Risk Corridor
* **Fact:** The green plausible band displayed on the Decision View uses quantile errors ($q_{10} = -549.3$ MW, $q_{90} = +4,300.2$ MW) calibrated across January 2026.
* **Caveat:** This is an operational heuristic intended to give traders a visual margin of safety. It is not a calibrated forward probabilistic meteorological ensemble.

---

### 5. Exclusion of Retrospective Forecasts
* **Fact:** In raw WINDFOR data, approximately 20% of records have `publish_time > start_time` (negative horizons where National Grid includes historical backcasts).
* **Treatment:** All retrospective records (`horizon_hours <= 0`) are filtered out from forward horizon evaluations.

---

## 8. Glossary

| Term | Definition |
| :--- | :--- |
| **BMRS** | **Balancing Mechanism Reporting Service.** The official web and API platform operated by Elexon providing operational data for the Great Britain electricity transmission system. |
| **BMU** | **Balancing Mechanism Unit.** The basic unit of trade and physical asset (generator, battery, or demand unit) registered in the UK Balancing Mechanism. |
| **Cash-Out Price** | The settlement price (System Buy Price or System Sell Price) applied to market participants whose contracted energy position does not equal their physical metered delivery. |
| **Cutoff Time** | The deadline on Day $D-1$ after which new forecast publications are ignored, simulating the point in time when auction bids are locked. |
| **Day $D$ / Day $D-1$** | **Day $D$** is the physical electricity delivery day. **Day $D-1$** is the day prior to delivery when wholesale auctions take place. |
| **Embedded Generation** | Smaller generators (e.g., small onshore wind farms or rooftop solar) connected to local distribution networks (DNOs) rather than the National Grid transmission system. |
| **Elexon** | The organization that administers the Balancing and Settlement Code (BSC) for Great Britain's electricity system. |
| **FUELHH** | Elexon's half-hourly generation outturn data stream categorized by fuel type (Wind, CCGT, Nuclear, Biomass, Solar, etc.). |
| **Horizon (Lead Time)** | The time difference in hours between when a forecast is published and when the power is actually delivered ($\text{startTime} - \text{publishTime}$). |
| **Long Position** | Having more contracted power than physical demand/generation ($\text{Actual} > \text{Forecast}$). The utility has surplus power and must sell it at System Sell Price. |
| **MAE** | **Mean Absolute Error.** The average magnitude of absolute forecast errors ($\frac{1}{N} \sum |\text{Error}|$). |
| **NESO (formerly National Grid ESO)** | **National Energy System Operator.** The independent system operator responsible for balancing the UK national electricity grid in real time. |
| **Net Demand** | Total consumer power consumption minus non-dispatchable renewable generation ($\text{Load} - \text{Wind}$). |
| **NMAE** | **Normalized Mean Absolute Error.** MAE divided by mean actual generation ($\text{MAE} / \overline{\text{Actual}}$). Used instead of MAPE to avoid zero-division errors. |
| **PPM** | **Power Park Module.** A group of wind turbines or solar panels connected to the system at a single connection point. |
| **P10 / P90** | The 10th and 90th percentiles of a statistical distribution. Used on this platform to represent empirical forecast error bounds. |
| **RMSE** | **Root Mean Squared Error.** The square root of the average squared errors ($\sqrt{\frac{1}{N}\sum \text{Error}^2}$). Strongly penalizes large outlier misses. |
| **Settlement Period (SP)** | The 30-minute operational time unit used in Great Britain power trading (48 periods per calendar day, numbered 1 to 48). |
| **Short Position** | Having less contracted power than physical demand ($\text{Actual} < \text{Forecast}$). The utility is deficient in power and must pay System Buy Prices. |
| **UTC** | **Coordinated Universal Time.** The time standard used across all database records and API endpoints. In January, Great Britain local time (GMT) is identical to UTC. |
| **WINDFOR** | Elexon's wind generation forecast data stream, published by National Grid ESO at regular intervals predicting future hourly wind output up to 72 hours ahead. |

---

## 9. Senior Engineer Coaching: How to Defend This in Your Tech Lead Review

When presenting to your technical lead, they will test your depth by asking sharp architectural and domain questions. Here is how you answer them like a seasoned senior engineer:

### Q1: "Why did you use SQLite instead of PostgreSQL or DuckDB?"
> **Your Answer:**  
> "For this evaluation platform, SQLite provides zero external infrastructure overhead, zero network latency, and ships inside Python’s standard library. It easily supports indexed relational queries with window functions (`ROW_NUMBER() OVER (...)`) to filter latest forecasts before cutoff timestamps. We run it in read-only mode (`mode=ro`) inside Docker for rock-solid concurrency without write locks. If this was scaled to live production streaming millions of half-hourly records across all European markets, I would migrate the time-series storage to TimescaleDB or ClickHouse with Redis caching."

### Q2: "Why is there a huge +1,852 MW positive bias? Did your code introduce a bug or miss a baseline?"
> **Your Answer:**  
> "No, the math and ingestion were thoroughly verified directly against raw Elexon API streams. The positive bias is a documented property of the datasets: Elexon's `FUELHH` stream only measures transmission-metered BMUs and excludes unmetered embedded wind generation connected to local distribution networks. `WINDFOR`, however, models total system wind. Furthermore, we checked the daily ratio of forecast to actual: it varies from 0.89 to 1.93 (median 1.14). Because it is not a constant scalar multiplier, we intentionally avoided applying an arbitrary synthetic offset. Instead, we document it transparently in the UI and methodology modal."

### Q3: "Why do cutoffs between 00:00 and 02:00 UTC have only 682 hours instead of 744 hours?"
> **Your Answer:**  
> "At 00:00 UTC on day $D-1$, the latest available forecast run from National Grid is the (D-2) 22:30 UTC run. National Grid publishes a 46.5-hour forward horizon in that run, which reaches up to 21:00 UTC on delivery day $D$. The last two hours of day $D$ (22:00 and 23:00 UTC) fall outside that forecast's reach and remain unforecasted until the 02:30 UTC run arrives. Across 31 days in January, that is exactly 62 missing hours ($744 - 62 = 682$). Rather than hiding or interpolating those hours, we explicitly compute both the like-for-like common set ($n=682$) and own-coverage set ($n=744$) so traders see the true liquidity and coverage impact."

### Q4: "Why did you evaluate at hourly resolution when actuals are published half-hourly?"
> **Your Answer:**  
> "WINDFOR forecasts are published only at 1-hour resolution. If we evaluated at 30-minute intervals, we would be forced to invent forecast numbers via spline or linear interpolation, creating artificial precision that National Grid never forecasted. Taking the arithmetic mean of the two half-hour actuals aligns the physical reality with the forecast window cleanly, while we preserve the raw 30-minute actuals in the database and API for high-resolution visual charting."

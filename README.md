# UK Wind Generation Forecast & Evaluation Platform

An end-to-end analytical and web platform designed for a UK energy utility's power trading desk. The platform evaluates National Grid ESO wind generation forecasts (`WINDFOR`) against actual metered outturns (`FUELHH` WIND) to quantify forecast error and timing risk for day-ahead electricity procurement.

- **Live Production Demo:** Deployed on **Vercel** (Hobby plan) at `<URL>` *(e.g., https://uk-wind-evaluator.vercel.app)*
- **Local Runs:** Docker multi-stage container (`Dockerfile`) and local development server.
- **Alternative Cloud Container:** Heroku Container Stack manifest (`heroku.yml`).

---

## Table of Contents
1. [Project Overview](#project-overview)
2. [Directory Structure](#directory-structure)
3. [Vercel Deployment Guide (Live Production Demo)](#vercel-deployment-guide-live-production-demo)
   - [Option 1: Deploy with Vercel Git Integration (Recommended)](#option-1-deploy-with-vercel-git-integration-recommended)
   - [Option 2: Deploy with Vercel CLI](#option-2-deploy-with-vercel-cli)
   - [Vercel Architecture & Zero-Config Runtimes](#vercel-architecture--zero-config-runtimes)
4. [How to Run Locally](#how-to-run-locally)
   - [Option A: Run with Docker (Local Container)](#option-a-run-with-docker-local-container)
   - [Option B: Local Development (Backend + Frontend)](#option-b-local-development-backend--frontend)
5. [Data Ingestion & Refresh](#data-ingestion--refresh)
6. [API Endpoint Summary](#api-endpoint-summary)
7. [Key Assumptions & Limitations](#key-assumptions--limitations)
8. [Heroku Container Deployment Guide (Alternative)](#heroku-container-deployment-guide-alternative)
9. [Automated Testing & CI](#automated-testing--ci)
10. [AI Tools Used](#ai-tools-used)

---

## Project Overview

In the Great Britain electricity market, energy buyers procure wholesale electricity on the day-ahead auction to cover forecasted consumer demand. Because wind generation is non-dispatchable with near-zero marginal operating cost, trading desks must determine **net demand** (total consumer load minus wind generation):

$$\text{Net Demand} = \text{System Demand} - \text{Wind Generation}$$

Accurate wind forecasts are critical:
- **Over-forecasting ($\text{Forecast} > \text{Actual}$):** The buyer expects more wind power than materializes, under-procures electricity on the day-ahead market, and is left **short** in real-time physical delivery, exposed to volatile Balancing Mechanism system buy prices (cash-out penalties).
- **Under-forecasting ($\text{Forecast} < \text{Actual}$):** The buyer over-procures power day-ahead and must spill or sell excess power at discounted system sell prices.

This platform provides:
1. **Decision-Time Forecast Visualization:** Displays the latest wind generation forecast available at the exact cutoff moment market purchase decisions are committed on day $D-1$.
2. **Empirical Risk Banding:** Overlays an in-sample P10–P90 plausible actual generation band onto the decision forecast to provide traders with a margin of safety.
3. **Quantitative Forecast Verification:** Computes MAE, RMSE, bias, error distributions, diurnal profiles, and horizon degradation across January 2026 delivery days.
4. **Decision Timing Sensitivity:** Evaluates how delaying purchasing decisions impacts forecast accuracy from D-1 00:00 to 23:00 UTC.

---

## Directory Structure

```text
energy_/
├── .github/
│   └── workflows/
│       └── ci.yml                  # GitHub Actions CI (Ruff, Pytest, Vitest, npm run build)
├── .dockerignore                   # Excludes dev files, node_modules, caches, and test artifacts
├── .gitignore                      # Git ignore rules (SQLite db data/wind_energy.db is tracked)
├── Dockerfile                      # Multi-stage container for local runs (Node 20 build + Python 3.11-slim)
├── heroku.yml                      # Heroku Container Stack manifest (alternative container host)
├── pyproject.toml                  # Python package metadata, ruff linter, and pytest configuration
├── vercel.json                     # Vercel project config (Vite static build, Python function, rewrites)
├── requirements.txt                # Vercel production Python function dependencies (FastAPI, Pandas, etc.)
├── README.md                       # Complete platform documentation and operational guide
├── api/
│   └── index.py                    # Vercel Serverless Function entrypoint exporting the FastAPI app
├── backend/
│   ├── requirements.txt            # Local/Docker Python dependencies
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                 # FastAPI application, static frontend SPA mount, and CORS setup
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── routes.py           # REST endpoints (/api/forecast, /api/compare, /api/metrics, etc.)
│   │   │   └── schemas.py          # Pydantic v2 validation models and response schemas
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   └── forecast_service.py # Business logic, cutoff filtering, hourly alignment, and metrics
│   │   └── ingest/
│   │       ├── __init__.py
│   │       ├── client.py           # Elexon BMRS API client with exponential backoff and rate-limiting
│   │       ├── cleaner.py          # UTC normalization, deduplication, and quality validation
│   │       ├── storage.py          # SQLite schema, read-only connections, and atomic transactions
│   │       └── pipeline.py         # Ingestion orchestration runner
│   └── tests/
│       ├── __init__.py
│       ├── test_api.py             # FastAPI route integration tests (endpoints, bounds, params)
│       ├── test_cleaner.py         # Data validation, type casting, and deduplication tests
│       └── test_services.py        # Business logic tests (cutoff filtering, hourly mean, bias, sign)
├── frontend/
│   ├── package.json                # Frontend dependencies (React 18, Vite, Recharts, Lucide)
│   ├── package-lock.json           # Pinned npm dependencies for deterministic builds
│   ├── vite.config.ts              # Vite configuration with /api reverse proxy to port 8000
│   ├── tsconfig.json               # TypeScript compiler options
│   ├── index.html                  # HTML entry point with modern dark typography
│   └── src/
│       ├── App.tsx                 # Main layout, view switching (Decision, Accuracy, Timing), and controls
│       ├── main.tsx                # React DOM root initialization
│       ├── index.css               # Bespoke design system tokens, CSS variables, and layout classes
│       ├── api/
│       │   └── client.ts           # Type-safe Fetch API client for backend communication
│       ├── types/
│       │   └── api.ts              # TypeScript interfaces mirroring backend Pydantic models
│       ├── utils/
│       │   ├── calculations.ts     # P10-P90 plausible range and error summary calculators
│       │   └── formatters.ts       # Megawatt, timestamp, and signed error formatters
│       ├── components/
│       │   ├── Navbar.tsx          # Top navigation bar, status indicator, and methodology trigger
│       │   ├── DecisionView.tsx    # Day-ahead decision forecast vs actuals with P10-P90 band
│       │   ├── AccuracyDashboard.tsx # Historical backtest KPIs, error histogram, and diurnal profiles
│       │   ├── HorizonTimingView.tsx # Lead-time degradation and D-1 cutoff sensitivity sweep
│       │   └── MethodologyModal.tsx # Commercial context, sign convention, and scope caveats drawer
│       └── tests/
│           └── calculations.test.ts # Vitest unit tests for calculations and formatting helpers
├── data/
│   └── wind_energy.db              # Self-contained SQLite snapshot (1,728 actuals, 23,944 forecasts)
├── notebooks/
│   └── 01_explore.ipynb            # Jupyter notebook analyzing dataset dimensions, horizons, and ramps
└── scripts/
    ├── run_ingest.py               # CLI entrypoint to fetch fresh data from Elexon BMRS
    ├── build_notebook.py           # Automated builder and runner for the exploration notebook
    └── verify_metrics.py           # Verification script for benchmark metrics calculation
```

---

## Vercel Deployment Guide (Live Production Demo)

The live production application runs on **Vercel** under the **Hobby (Free)** plan with zero hosting fees. Docker (`Dockerfile`) and Heroku (`heroku.yml`) are preserved for local development and containerized environments.

### Option 1: Deploy with Vercel Git Integration (Recommended)

1. Push your repository to GitHub, GitLab, or Bitbucket:
   ```bash
   git add .
   git commit -m "feat: port deployment to Vercel"
   git push origin main
   ```
2. Navigate to [vercel.com/new](https://vercel.com/new) and log in.
3. Import your `energy_` repository.
4. Vercel automatically detects `vercel.json`. Leave the Project Settings at defaults:
   - **Framework Preset:** Other
   - **Root Directory:** `./`
   - **Build Command:** `cd frontend && npm install && npm run build` (configured automatically via `vercel.json`)
   - **Output Directory:** `frontend/dist` (configured automatically via `vercel.json`)
5. Click **Deploy**. Vercel will install dependencies, build the React SPA, package the Python serverless function, and assign a production URL (e.g., `https://<your-project>.vercel.app`).

---

### Option 2: Deploy with Vercel CLI

If you prefer deploying from your terminal without connecting Git:

1. Install the Vercel CLI globally:
   ```bash
   npm install -g vercel
   ```
2. Log in to your Vercel account:
   ```bash
   vercel login
   ```
3. Deploy preview build:
   ```bash
   vercel
   ```
   *Respond to the interactive prompts:*
   - Set up and deploy? **Y**
   - Which scope? *(select your personal account)*
   - Link to existing project? **N**
   - What's your project's name? **uk-wind-evaluator**
   - In which directory is your code located? **./**
   - Want to modify settings? **N** (Vercel reads `vercel.json`)
4. Deploy directly to production:
   ```bash
   vercel --prod
   ```

---

### Vercel Architecture & Zero-Config Runtimes

| Component | Host / Runtime | Configuration |
| :--- | :--- | :--- |
| **Frontend SPA** | Vercel Edge Network (Static CDN) | Built via `cd frontend && npm run build` -> `frontend/dist`. Single-Page App rewrites direct non-API paths (`/(.*)`) to `/index.html`. |
| **Backend API** | Vercel Python Runtime (`python3.12`) | Entrypoint `api/index.py` exposes the FastAPI ASGI `app`. `/api/(.*)` routes to `api/index.py`. |
| **Database** | SQLite Read-Only Snapshot | `data/wind_energy.db` (5.8 MB) is bundled into the function via `includeFiles` in `vercel.json` and opened with `uri=True` using `file:...mode=ro`. No `/tmp` storage or write permissions needed. |
| **Bundle Size** | Serverless Function (< 500 MB limit) | Root `requirements.txt` installs only lean runtime dependencies (`fastapi`, `uvicorn`, `pydantic`, `pandas`, `requests`). Development packages (`matplotlib`, `ipykernel`) are excluded, keeping the total uncompressed package size under 80 MB. |

---

## How to Run Locally

### Option A: Run with Docker (Local Container)

The project includes a multi-stage `Dockerfile` that compiles the React frontend into static assets and packages the FastAPI backend, pre-populated SQLite database, and Uvicorn runtime into a self-contained image running as a secure non-root user.

```bash
# 1. Build the Docker container image
docker build -t uk-wind-evaluator .

# 2. Run the container locally (mapping host port 8080 to container port 8080)
docker run -p 8080:8080 uk-wind-evaluator
```

Once running, access the services:
- **Interactive Web Application:** [http://localhost:8080](http://localhost:8080)
- **API Health Check:** [http://localhost:8080/api/health](http://localhost:8080/api/health)
- **Interactive OpenAPI Documentation:** [http://localhost:8080/docs](http://localhost:8080/docs)
- **January 2026 Metrics JSON:**
  ```bash
  curl "http://localhost:8080/api/metrics?start=2026-01-01&end=2026-01-31&cutoff_hour=9"
  ```

---

### Option B: Local Development (Backend + Frontend)

For local development with live code reloading:

#### 1. Backend Setup (FastAPI)
```bash
# Ensure Python 3.11+ is installed
python --version

# Install backend dependencies
pip install -r backend/requirements.txt

# Start FastAPI development server with auto-reload
python -m uvicorn backend.app.main:app --reload --port 8000
```
* Backend runs at: [http://localhost:8000](http://localhost:8000)
* Interactive Swagger Docs: [http://localhost:8000/docs](http://localhost:8000/docs)

#### 2. Frontend Setup (React + Vite)
In a separate terminal window:
```bash
cd frontend

# Install pinned dependencies
npm install

# Start Vite development server
npm run dev
```
* Frontend interface runs at: [http://localhost:5173](http://localhost:5173)
* The Vite dev server automatically proxies all `/api/*` requests to `http://localhost:8000`.

---

## Data Ingestion & Refresh

The repository comes pre-loaded with an offline SQLite snapshot (`data/wind_energy.db`) covering the entire test window (1,728 half-hourly actuals from 30 Dec 2025 to 03 Feb 2026 and 23,944 WINDFOR forecasts).

To refresh or expand the data from the live public Elexon BMRS API:
```bash
python scripts/run_ingest.py --start-date 2025-12-30 --end-date 2026-02-03 --chunk-days 7
```
**Ingestion Features:**
- Queries `FUELHH` (`fuelType = "WIND"`) and `WINDFOR` endpoints with query chunking.
- Handles exponential backoff on HTTP 429 and 5xx responses.
- Deduplicates rows on primary keys (`start_time` for actuals; `start_time, publish_time` for forecasts).
- Validates that zero half-hourly settlement intervals are missing across the target range.

---

## API Endpoint Summary

All timestamps, query parameters, and database operations execute strictly in **UTC**.

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/health` | Returns service status, snapshot row counts, and date coverage bounds. |
| `GET` | `/api/actuals` | Raw 30-minute metered actuals (`FUELHH` WIND) for high-resolution charting. |
| `GET` | `/api/forecast/latest` | 24 hourly slots for `delivery_date` with the latest forecast published on or before D-1 `cutoff_hour:00 UTC`. |
| `GET` | `/api/compare` | Detailed hourly comparison of decision forecast vs mean hourly actuals, including error, publish times, and run bounds. |
| `GET` | `/api/metrics` | Aggregate accuracy metrics (MAE, RMSE, bias, P50/P90/P95 abs error, P05..P95 signed error quantiles, coverage, normalized MAE). |
| `GET` | `/api/metrics/by-cutoff`| Sensitivity analysis evaluating MAE and bias across decision cutoffs from D-1 00:00 to 23:00 UTC. |
| `GET` | `/api/metrics/daily` | Day-by-day breakdown of mean actual, mean forecast, bias, and MAE across delivery days. |
| `GET` | `/api/error-distribution`| Signed forecast error histogram in 500 MW bins. |
| `GET` | `/api/metrics/by-horizon`| Accuracy bucketed by forecast lead time (0-6h, 6-12h, 12-24h, 24-36h, 36-48h, 48h+). Negative horizons excluded. |
| `GET` | `/api/metrics/by-hour` | Diurnal profile of MAE and bias across the 24 settlement hours of the day (00:00 to 23:00 UTC). |

---

## Key Assumptions & Limitations

### 1. Market Decision Cutoff Rule
- For power delivery on day **$D$**, the commercial procurement desk commits purchasing volumes on day **$D-1$** at a cutoff time (default: **09:00 UTC**).
- For each target settlement slot in day $D$, the eligible decision forecast is strictly the latest publication satisfying:
  $$\text{publish\_time} \le \text{cutoff\_timestamp (D-1 at cutoff\_hour:00 UTC)}$$
- **Assumed Gate Closure Constant & Like-for-Like Timing Sensitivity:**
  The platform configures `ASSUMED_GATE_CLOSURE_HOUR_UTC = 9` (documented as an **unverified operational assumption**). Because cutoffs 00:00 to 02:00 UTC have 91.7% coverage (682/744 hours, see payload explanation below), a true like-for-like evaluation is computed on the **common set of 682 delivery hours** forecasted across all 24 cutoffs:
  - **(a) Actionable Window (D-1 00:00 to assumed gate closure at 09:00 UTC, $n=682$ common hours):** Forecast MAE drops from **2,216 MW** at 00:00 to **2,157 MW** at 09:00 (a like-for-like reduction of **59 MW**, or **2.7%**). *(On unaligned own-coverage of 744 hours, Cutoff 9 MAE is 2,142 MW).*
  - **(b) Informational Window (beyond assumed gate closure, 09:00 to 23:00 UTC, $n=682$ common hours):** Forecast MAE further decreases from **2,157 MW** at 09:00 to **1,931 MW** at 23:00 (a further reduction of **226 MW**, or **10.5%**). *(On unaligned own-coverage of 744 hours, Cutoff 23 MAE is 1,936 MW).*
  - **Total 24h Sensitivity ($n=682$ common hours):** Across the day from 00:00 to 23:00 UTC, MAE decreases from **2,216 MW** to **1,931 MW** (an overall like-for-like reduction of **285 MW**, or **12.8%**).
- **Why Cutoffs 00:00–02:00 UTC Have 62 Unforecasted Hours (91.7% Coverage):**
  - For delivery on day $D$, the D-1 00:00 UTC cutoff selects the latest forecast run published before midnight, which is strictly the **(D-2) at 22:30 UTC run**.
  - National Grid ESO's 73-step WINDFOR payload includes retrospective steps from -25.5h in the past and extends forward to +46.5h ahead.
  - Exactly 46.5 hours ahead of (D-2) 22:30 UTC is **delivery day $D$ at 21:00 UTC**.
  - Delivery slots **22:00 UTC and 23:00 UTC exceed the forward reach of the (D-2) 22:30 UTC payload** (+47.5h and +48.5h lead times). These two slots remain unforecasted until the (D-1) 02:30 UTC run arrives. Across all 31 days in January 2026, exactly those 2 hours per day ($31 \times 2 = \mathbf{62\text{ hours}}$) lack an eligible forecast at cutoffs 00:00, 01:00, and 02:00 UTC. The platform explicitly highlights these cutoffs on the sensitivity chart and provides both common-set and own-coverage metrics.

### 2. Hourly Resolution Alignment
- `WINDFOR` forecasts are published at hourly intervals (73 hourly steps from 0h to 72h ahead), whereas `FUELHH` actuals are settled at half-hourly intervals.
- In all evaluation metrics and comparison endpoints, data is aligned at **hourly resolution**:
  - A forecast with `startTime` $T$ covers the 1-hour interval $[T, T + 1\text{h})$.
  - The hourly actual is computed as the arithmetic mean of the two half-hour actuals in that hour:
    $$\text{Actual}_{\text{hourly}}(T) = \frac{\text{Actual}(T) + \text{Actual}(T + 30\text{m})}{2}$$
  - **Coverage** is defined as $\text{forecasted\_hours} / \text{total\_hours}$. An unforecasted hour indicates that no eligible forecast run was published before the decision cutoff.

### 3. Strict UTC Time Standard
- All timestamps, queries, and calculations operate in **UTC** without exception.
- In January, Great Britain local time (GMT) is identical to UTC ($0\text{h}$ offset).

### 4. Error Sign Convention & Trading Position
- Forecast error is defined uniformly as:
  $$\text{Error} = \text{Forecast} - \text{Actual}$$
- **Commercial Impact:** A positive error indicates an **over-forecast**. The buyer expected more wind generation than materialized, resulting in under-procurement on the day-ahead auction. This leaves the trading desk in a **short position** during real-time delivery, exposed to system cash-out balancing mechanism costs.

### 5. Critical Scope Differences & Bias Interpretation
- A persistent positive bias (+1,852 MW mean error in January 2026 at the 09:00 UTC cutoff) is observed across all horizons and delivery days.
- **Data Definition Mismatch:**
  - `FUELHH` (Actuals): Elexon documentation states that FUELHH originates from operational metering for Balancing Mechanism Units (BMUs) connected directly to the transmission system: *"Renewable generation figures can be underestimated because the dataset excludes embedded generation and wind farms that lack operational meters."*
  - `WINDFOR` (Forecasts): Defined by Elexon as *"A forecast of generation output for all Power Park Modules (PPMs) connected to the system."*
- **Caveat:** The positive bias may partly reflect these structural scope differences (metered transmission wind vs. total system wind) and partly atmospheric forecast error; the available public stream data cannot separate the two.
- **Empirical Ratio Variation:** The daily forecast/actual ratio varies widely across the month: **22 of 31 days fall between 1.07 and 1.35**, with an overall range of **0.89 to 1.93** (median **1.14**). Because of this wide day-to-day variation, a constant-scope explanation alone is not supported. We state only computed figures and do not assert an unverified cause.

### 6. In-Sample Backtest Band Limitation
- The P10–P90 plausible actual wind generation band displayed on the Decision View is calibrated in-sample using historical errors from the January 2026 evaluation window.
- It is intended as an operational heuristic rather than a validated forward probabilistic model.

### 7. Exclusion of Retrospective Forecasts
- In raw WINDFOR publications, approximately 20% of records have $\text{publish\_time} > \text{start\_time}$ (negative forecast horizons, where National Grid ESO models include historical backcasts).
- All retrospective records are strictly excluded from forward horizon evaluations.

---

## Heroku Container Deployment Guide (Alternative)

The application is also container-ready for Heroku using Heroku's Docker Container Stack via `heroku.yml`.

### Step-by-Step Deployment Instructions

```bash
# 1. Log in to the Heroku CLI
heroku login

# 2. Log in to the Heroku Container Registry
heroku container:login

# 3. Create a new Heroku application
heroku create uk-wind-forecast-app

# 4. Set the application stack to 'container'
heroku stack:set container --app uk-wind-forecast-app

# 5. Deploy via Git (Heroku builds the multi-stage Dockerfile automatically)
git push heroku main

# Alternatively, deploy directly using Heroku Container Registry:
# heroku container:push web --app uk-wind-forecast-app
# heroku container:release web --app uk-wind-forecast-app

# 6. Open the deployed application in your browser
heroku open --app uk-wind-forecast-app
```

> [!IMPORTANT]
> **Heroku Pricing Notice:** Heroku requires a paid dyno plan (e.g., Eco or Basic dyno). Please verify current Heroku pricing and dyno limits before provisioning resources.

---

## Automated Testing & CI

Continuous Integration is configured via GitHub Actions (`.github/workflows/ci.yml`) and runs automatically on all pushes and pull requests to `main`.

### Local Test Execution

```bash
# 1. Run Python code linting (Ruff)
ruff check .

# 2. Run backend pytest suite (17 tests covering API, services, cleaning, and errors)
pytest backend/tests -v

# 3. Run frontend vitest suite (4 tests covering formatting and calculations)
cd frontend && npm test -- --run

# 4. Verify frontend production TypeScript build
cd frontend && npm run build
```

---

## AI Tools Used

This project was engineered with assistance from:
- **Google Antigravity (Gemini):** Used as the primary agentic pair-programmer for end-to-end implementation, including Elexon BMRS ingestion pipelines, SQLite schema design, FastAPI services and endpoints, React/TypeScript interface design, Recharts interactive visualizations, unit test suites, and Docker containerization.
- **Claude (Anthropic):** Utilized for independent architecture planning, prompt review, methodology critique, and verification of key commercial assumptions.

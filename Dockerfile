# -------------------------------------------------------------
# Stage 1: Build React Frontend
# -------------------------------------------------------------
FROM node:20.18-alpine AS frontend-builder

WORKDIR /build/frontend

# Install dependencies using package-lock.json for reproducible builds
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# Copy frontend source and compile static production bundle
COPY frontend/ ./
RUN npm run build

# -------------------------------------------------------------
# Stage 2: Python Backend Runtime
# -------------------------------------------------------------
FROM python:3.11-slim AS runtime

# Set Python environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8080

WORKDIR /app

# Create non-root system group and user
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

# Install backend dependencies
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Copy backend application code and SQLite database snapshot
COPY backend/ /app/backend/
COPY data/wind_energy.db /app/data/wind_energy.db

# Copy compiled static frontend distribution from Stage 1
COPY --from=frontend-builder /build/frontend/dist /app/frontend/dist

# Change ownership of /app to non-root user
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose default port (Heroku dynamically injects $PORT at runtime)
EXPOSE 8080

# Health check using Python stdlib urllib to test /api/health
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request, os; port = os.environ.get('PORT', '8080'); urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health')" || exit 1

# Run Uvicorn listening on 0.0.0.0 and the PORT environment variable
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]

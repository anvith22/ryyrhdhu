/**
 * Typed HTTP client communicating with FastAPI backend.
 * Uses relative URL /api which Vite dev server proxies to http://localhost:8000.
 */

import {
  ActualsResponse,
  CompareResponse,
  ErrorDistributionResponse,
  HealthResponse,
  MetricsByCutoffResponse,
  MetricsByHorizonResponse,
  MetricsByHourResponse,
  MetricsDailyResponse,
  MetricsResponse,
} from '../types/api';

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    let errorDetail = `HTTP ${res.status}: ${res.statusText}`;
    try {
      const errJson = await res.json();
      if (errJson.detail) {
        errorDetail = typeof errJson.detail === 'string' ? errJson.detail : JSON.stringify(errJson.detail);
      }
    } catch {
      // ignore json parse error
    }
    throw new Error(errorDetail);
  }
  return res.json();
}

export const apiClient = {
  getHealth: (): Promise<HealthResponse> => {
    return fetchJson<HealthResponse>('/api/health');
  },

  getActuals: (start: string, end: string): Promise<ActualsResponse> => {
    return fetchJson<ActualsResponse>(`/api/actuals?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`);
  },

  getCompare: (deliveryDate: string, cutoffHour: number = 9): Promise<CompareResponse> => {
    return fetchJson<CompareResponse>(
      `/api/compare?delivery_date=${encodeURIComponent(deliveryDate)}&cutoff_hour=${cutoffHour}`
    );
  },

  getMetrics: (start: string, end: string, cutoffHour: number = 9): Promise<MetricsResponse> => {
    return fetchJson<MetricsResponse>(
      `/api/metrics?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&cutoff_hour=${cutoffHour}`
    );
  },

  getMetricsByCutoff: (start: string, end: string): Promise<MetricsByCutoffResponse> => {
    return fetchJson<MetricsByCutoffResponse>(
      `/api/metrics/by-cutoff?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`
    );
  },

  getMetricsDaily: (start: string, end: string, cutoffHour: number = 9): Promise<MetricsDailyResponse> => {
    return fetchJson<MetricsDailyResponse>(
      `/api/metrics/daily?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&cutoff_hour=${cutoffHour}`
    );
  },

  getMetricsByHorizon: (start: string, end: string): Promise<MetricsByHorizonResponse> => {
    return fetchJson<MetricsByHorizonResponse>(
      `/api/metrics/by-horizon?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`
    );
  },

  getMetricsByHour: (start: string, end: string, cutoffHour: number = 9): Promise<MetricsByHourResponse> => {
    return fetchJson<MetricsByHourResponse>(
      `/api/metrics/by-hour?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&cutoff_hour=${cutoffHour}`
    );
  },

  getErrorDistribution: (start: string, end: string, cutoffHour: number = 9): Promise<ErrorDistributionResponse> => {
    return fetchJson<ErrorDistributionResponse>(
      `/api/error-distribution?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&cutoff_hour=${cutoffHour}`
    );
  },
};

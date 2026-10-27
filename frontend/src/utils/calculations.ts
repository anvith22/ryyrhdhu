/**
 * Quantile prediction band calculations for power purchasing decisions.
 */

export interface PlausibleBand {
  lower: number | null;
  upper: number | null;
  bandHeight: number | null;
}

/**
 * Calculates the plausible actual wind generation range (P10-P90 backtest band)
 * based on the empirical signed error quantiles:
 * error = forecast - actual  =>  actual = forecast - error
 *
 * Plausible Lower Bound = max(0, forecast - q90)
 * Plausible Upper Bound = max(0, forecast - q10)
 */
export function calculatePlausibleBand(
  forecastMw: number | null | undefined,
  q10: number | null | undefined,
  q90: number | null | undefined
): PlausibleBand {
  if (forecastMw === null || forecastMw === undefined || q10 === null || q90 === null || q10 === undefined || q90 === undefined) {
    return { lower: null, upper: null, bandHeight: null };
  }

  const rawLower = forecastMw - q90;
  const rawUpper = forecastMw - q10;

  const lower = Math.max(0, Math.round(rawLower * 10) / 10);
  const upper = Math.max(0, Math.round(rawUpper * 10) / 10);
  const bandHeight = Math.max(0, Math.round((upper - lower) * 10) / 10);

  return { lower, upper, bandHeight };
}

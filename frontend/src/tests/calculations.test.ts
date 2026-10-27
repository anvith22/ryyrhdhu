import { describe, it, expect } from 'vitest';
import { calculatePlausibleBand } from '../utils/calculations';
import { formatMW, formatSignedMW, formatTimeUTC } from '../utils/formatters';

describe('Frontend Calculation and Formatting Utilities', () => {
  it('correctly calculates plausible actual quantile band (P10-P90)', () => {
    // When forecast is 12,000 MW, q10 is -500 MW, and q90 is +3,000 MW
    // Plausible lower = forecast - q90 = 12,000 - 3,000 = 9,000 MW
    // Plausible upper = forecast - q10 = 12,000 - (-500) = 12,500 MW
    const band = calculatePlausibleBand(12000, -500, 3000);
    expect(band.lower).toBe(9000);
    expect(band.upper).toBe(12500);
    expect(band.bandHeight).toBe(3500);
  });

  it('bounds lower quantile prediction band at zero to prevent negative power', () => {
    // When forecast is 1,000 MW and q90 error is 2,500 MW
    // forecast - q90 = -1,500 MW => should clamp to 0
    const band = calculatePlausibleBand(1000, 200, 2500);
    expect(band.lower).toBe(0);
    expect(band.upper).toBe(800);
    expect(band.bandHeight).toBe(800);
  });

  it('formats power generation and signed errors correctly', () => {
    expect(formatMW(14500.4)).toBe('14,500 MW');
    expect(formatMW(null)).toBe('—');
    expect(formatSignedMW(1850)).toBe('+1,850 MW');
    expect(formatSignedMW(-320)).toBe('-320 MW');
  });

  it('formats UTC time correctly regardless of local machine timezone', () => {
    const formatted = formatTimeUTC('2026-01-15T09:30:00Z');
    expect(formatted).toBe('09:30 UTC');
  });
});

/**
 * Formatting and CSV export utilities.
 */

import { CompareSlot } from '../types/api';

export function formatMW(val: number | null | undefined): string {
  if (val === null || val === undefined || isNaN(val)) return '—';
  return `${Math.round(val).toLocaleString()} MW`;
}

export function formatMWh(val: number | null | undefined): string {
  if (val === null || val === undefined || isNaN(val)) return '—';
  return `${Math.round(val).toLocaleString()} MWh`;
}

export function formatPercent(val: number | null | undefined): string {
  if (val === null || val === undefined || isNaN(val)) return '—';
  return `${(val * 100).toFixed(1)}%`;
}

export function formatSignedMW(val: number | null | undefined): string {
  if (val === null || val === undefined || isNaN(val)) return '—';
  const prefix = val > 0 ? '+' : '';
  return `${prefix}${Math.round(val).toLocaleString()} MW`;
}

export function formatTimeUTC(isoString: string | null | undefined): string {
  if (!isoString) return '—';
  try {
    const dt = new Date(isoString);
    const hours = String(dt.getUTCHours()).padStart(2, '0');
    const mins = String(dt.getUTCMinutes()).padStart(2, '0');
    return `${hours}:${mins} UTC`;
  } catch {
    return isoString;
  }
}

export function formatDateTimeUTC(isoString: string | null | undefined): string {
  if (!isoString) return '—';
  try {
    const dt = new Date(isoString);
    const day = String(dt.getUTCDate()).padStart(2, '0');
    const month = dt.toLocaleString('en-GB', { month: 'short', timeZone: 'UTC' });
    const hours = String(dt.getUTCHours()).padStart(2, '0');
    const mins = String(dt.getUTCMinutes()).padStart(2, '0');
    return `${day} ${month} ${hours}:${mins} UTC`;
  } catch {
    return isoString;
  }
}

export function exportSlotsToCSV(slots: CompareSlot[], deliveryDate: string): void {
  const headers = [
    'Slot Time (UTC)',
    'Target Hour (UTC)',
    'Actual Generation (MW)',
    'Forecast Generation (MW)',
    'Forecast Error (MW)',
    'Abs Error (MW)',
    'Publish Time (UTC)',
    'Forecast Horizon (Hours)',
  ];

  const rows = slots.map((s) => [
    s.start_time,
    s.target_hour_utc,
    s.actual_mw ?? '',
    s.forecast_mw ?? '',
    s.error_mw ?? '',
    s.abs_error_mw ?? '',
    s.publish_time ?? '',
    s.horizon_hours ?? '',
  ]);

  const csvContent =
    'data:text/csv;charset=utf-8,' +
    [headers.join(','), ...rows.map((e) => e.join(','))].join('\n');

  const encodedUri = encodeURI(csvContent);
  const link = document.createElement('a');
  link.setAttribute('href', encodedUri);
  link.setAttribute('download', `wind_forecast_compare_${deliveryDate}.csv`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

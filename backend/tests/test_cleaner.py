"""Unit tests for FUELHH and WINDFOR data cleaning functions.

Supports both pytest and standard python unittest test runners.
"""

import unittest

import pandas as pd

try:
    import pytest
except ImportError:
    pytest = None

from backend.app.ingest.cleaner import clean_fuelhh, clean_windfor, find_missing_30min_slots


class TestDataCleaning(unittest.TestCase):
    """Test suite for ingestion cleaner functions."""

    def test_clean_fuelhh_parsing_types_and_deduplication(self):
        """Verify clean_fuelhh parses timestamps to UTC, casts numeric generation, and deduplicates."""
        raw_records = [
            {
                "dataset": "FUELHH",
                "startTime": "2026-01-01T00:00:00Z",
                "publishTime": "2026-01-01T01:00:00Z",
                "settlementDate": "2026-01-01",
                "settlementPeriod": 1,
                "fuelType": "WIND",
                "generation": "12500",  # String number to verify type coercion
            },
            # Duplicate startTime with later publishTime to verify deduplication
            {
                "dataset": "FUELHH",
                "startTime": "2026-01-01T00:00:00Z",
                "publishTime": "2026-01-01T01:30:00Z",
                "settlementDate": "2026-01-01",
                "settlementPeriod": 1,
                "fuelType": "WIND",
                "generation": 12550,
            },
            # Invalid non-numeric record to verify error handling
            {
                "dataset": "FUELHH",
                "startTime": "2026-01-01T00:30:00Z",
                "publishTime": "2026-01-01T01:00:00Z",
                "settlementDate": "2026-01-01",
                "settlementPeriod": 2,
                "fuelType": "WIND",
                "generation": "INVALID_NUM",
            },
        ]

        df_clean, df_missing = clean_fuelhh(raw_records)

        # Only 1 valid record should remain (duplicate resolved, invalid dropped)
        self.assertEqual(len(df_clean), 1)
        row = df_clean.iloc[0]

        # Timestamp must be UTC
        self.assertIsNotNone(row["start_time"].tzinfo)
        self.assertEqual(row["start_time"], pd.Timestamp("2026-01-01 00:00:00", tz="UTC"))

        # Generation must be numeric float/int with value from later publication
        self.assertIsInstance(row["generation_mw"], (float, int))
        self.assertEqual(row["generation_mw"], 12550.0)
        self.assertEqual(row["settlement_period"], 1)

    def test_find_missing_30min_slots(self):
        """Verify find_missing_30min_slots flags omitted half-hour settlement intervals."""
        # 00:00 and 01:00 present, but 00:30 is missing
        slots = pd.Series([
            pd.Timestamp("2026-01-01 00:00:00", tz="UTC"),
            pd.Timestamp("2026-01-01 01:00:00", tz="UTC"),
        ])

        missing = find_missing_30min_slots(
            slots,
            expected_start=pd.Timestamp("2026-01-01 00:00:00", tz="UTC"),
            expected_end=pd.Timestamp("2026-01-01 01:00:00", tz="UTC"),
        )

        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0], pd.Timestamp("2026-01-01 00:30:00", tz="UTC"))

    def test_clean_windfor_horizon_and_quality_checks(self):
        """Verify clean_windfor computes forecast horizon and produces quality reports."""
        raw_forecasts = [
            # Normal day-ahead forecast (published 24 hours prior)
            {
                "dataset": "WINDFOR",
                "startTime": "2026-01-02T12:00:00Z",
                "publishTime": "2026-01-01T12:00:00Z",
                "generation": 14200,
            },
            # Duplicate record
            {
                "dataset": "WINDFOR",
                "startTime": "2026-01-02T12:00:00Z",
                "publishTime": "2026-01-01T12:00:00Z",
                "generation": 14200,
            },
            # Negative generation anomaly
            {
                "dataset": "WINDFOR",
                "startTime": "2026-01-02T12:30:00Z",
                "publishTime": "2026-01-01T12:00:00Z",
                "generation": -10,
            },
            # Outturn retrospective publication (startTime before publishTime)
            {
                "dataset": "WINDFOR",
                "startTime": "2026-01-01T10:00:00Z",
                "publishTime": "2026-01-01T12:00:00Z",
                "generation": 11000,
            },
        ]

        df_clean, quality_report = clean_windfor(raw_forecasts)

        # 4 records -> 1 duplicate removed -> 3 rows
        self.assertEqual(len(df_clean), 3)
        self.assertEqual(quality_report["duplicates_removed"], 1)
        self.assertEqual(quality_report["negative_generation_count"], 1)
        self.assertEqual(quality_report["negative_horizon_count"], 1)

        # Check horizon calculation (24.0 hours)
        first_row = df_clean[
            (df_clean["start_time"] == pd.Timestamp("2026-01-02 12:00:00", tz="UTC"))
            & (df_clean["publish_time"] == pd.Timestamp("2026-01-01 12:00:00", tz="UTC"))
        ].iloc[0]

        if pytest is not None:
            self.assertEqual(pytest.approx(first_row["horizon_hours"], 0.01), 24.0)
        else:
            self.assertAlmostEqual(first_row["horizon_hours"], 24.0, places=2)


if __name__ == "__main__":
    unittest.main()

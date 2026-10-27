"""CLI script to run data ingestion from Elexon BMRS API.

Usage:
    py scripts/run_ingest.py
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.ingest.pipeline import run_ingest  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch, clean, and store UK wind actuals and forecasts from Elexon BMRS."
    )
    parser.add_argument(
        "--start-date",
        type=lambda s: date.fromisoformat(s),
        default=date(2025, 12, 30),
        help="Start settlement date for FUELHH actuals (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        type=lambda s: date.fromisoformat(s),
        default=date(2026, 2, 3),
        help="End settlement date for FUELHH actuals (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--publish-from",
        type=lambda s: datetime.fromisoformat(s).replace(tzinfo=timezone.utc),
        default=datetime(2025, 12, 25, 0, 0, 0, tzinfo=timezone.utc),
        help="Start publish timestamp for WINDFOR forecasts (ISO 8601 UTC)",
    )
    parser.add_argument(
        "--publish-to",
        type=lambda s: datetime.fromisoformat(s).replace(tzinfo=timezone.utc),
        default=datetime(2026, 2, 3, 23, 59, 59, tzinfo=timezone.utc),
        help="End publish timestamp for WINDFOR forecasts (ISO 8601 UTC)",
    )
    parser.add_argument(
        "--chunk-days",
        type=int,
        default=7,
        help="Date window chunk size in days for API streaming queries",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    args = parse_args()

    print("\n" + "=" * 60)
    print("UK Energy Utility - Wind Generation & Forecast Ingest")
    print(f"Settlement Dates: {args.start_date} to {args.end_date}")
    print(f"Forecast Publish: {args.publish_from.isoformat()} to {args.publish_to.isoformat()}")
    print("=" * 60 + "\n")

    summary = run_ingest(
        start_date=args.start_date,
        end_date=args.end_date,
        forecast_publish_from=args.publish_from,
        forecast_publish_to=args.publish_to,
        chunk_days=args.chunk_days,
    )

    print("\n" + "=" * 60)
    print("Ingestion Summary:")
    print(json.dumps(summary, indent=2))
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()

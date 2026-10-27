"""Elexon BMRS API client for FUELHH and WINDFOR streams.

All timestamps and queries handled by this client are in UTC.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Generator

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

logger = logging.getLogger(__name__)

# Base endpoint for Elexon Insights Solution (BMRS) API
DEFAULT_BASE_URL = "https://data.elexon.co.uk/bmrs/api/v1"


class ElexonClient:
    """Client for pulling public generation and forecast streams from Elexon BMRS."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: int = 45,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

        # Configure session with exponential backoff retries for transient HTTP errors (e.g. 429, 502, 503, 504)
        self.session = requests.Session()
        retries = Retry(
            total=max_retries,
            backoff_factor=backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def _get_json(self, endpoint: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Internal GET helper executing requests with logging and error handling."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        logger.debug("Requesting %s with params %s", url, params)

        response = self.session.get(url, params=params, timeout=self.timeout_seconds)
        response.raise_for_status()

        data = response.json()
        if isinstance(data, list):
            return data
        # Handle cases where API wraps data in a top-level key
        if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
            return data["data"]
        raise ValueError(f"Unexpected response structure from {url}: {type(data)}")

    @staticmethod
    def _chunk_dates(start_date: date, end_date: date, chunk_days: int = 7) -> Generator[tuple[date, date], None, None]:
        """Split a date range into smaller sub-ranges to avoid oversized HTTP responses or gateway timeouts."""
        current = start_date
        while current <= end_date:
            chunk_end = min(current + timedelta(days=chunk_days - 1), end_date)
            yield current, chunk_end
            current = chunk_end + timedelta(days=1)

    @staticmethod
    def _chunk_datetimes(
        start_dt: datetime, end_dt: datetime, chunk_days: int = 7
    ) -> Generator[tuple[datetime, datetime], None, None]:
        """Split a UTC datetime range into chunked datetime windows."""
        current = start_dt
        while current < end_dt:
            chunk_end = min(current + timedelta(days=chunk_days), end_dt)
            yield current, chunk_end
            current = chunk_end

    def fetch_fuelhh_wind(
        self,
        start_date: date,
        end_date: date,
        chunk_days: int = 7,
    ) -> list[dict[str, Any]]:
        """Fetch actual half-hourly wind generation from FUELHH stream.

        Elexon's FUELHH stream filters by settlementDateFrom and settlementDateTo (YYYY-MM-DD).
        Results are client-filtered for fuelType == 'WIND' to minimize memory consumption.
        """
        all_records: list[dict[str, Any]] = []

        logger.info(
            "Fetching FUELHH (WIND) from %s to %s in %d-day chunks",
            start_date,
            end_date,
            chunk_days,
        )

        for chunk_start, chunk_end in self._chunk_dates(start_date, end_date, chunk_days=chunk_days):
            params = {
                "settlementDateFrom": chunk_start.isoformat(),
                "settlementDateTo": chunk_end.isoformat(),
            }
            logger.info("Fetching FUELHH chunk: %s to %s", chunk_start, chunk_end)
            data = self._get_json("datasets/FUELHH/stream", params=params)

            # Keep only national wind generation
            wind_rows = [item for item in data if item.get("fuelType") == "WIND"]
            logger.info(
                "Retrieved %d FUELHH records for chunk (%d WIND records)",
                len(data),
                len(wind_rows),
            )
            all_records.extend(wind_rows)

        logger.info("Completed FUELHH fetch. Total wind records retrieved: %d", len(all_records))
        return all_records

    def fetch_windfor(
        self,
        publish_from: datetime,
        publish_to: datetime,
        chunk_days: int = 7,
    ) -> list[dict[str, Any]]:
        """Fetch wind forecasts from WINDFOR stream.

        Elexon's WINDFOR stream filters by publishDateTimeFrom and publishDateTimeTo (ISO 8601 UTC).
        Each publication contains forecast half-hourly generation profiles across upcoming days.
        """
        all_records: list[dict[str, Any]] = []

        # Ensure datetimes are explicitly marked as UTC
        if publish_from.tzinfo is None:
            publish_from = publish_from.replace(tzinfo=timezone.utc)
        if publish_to.tzinfo is None:
            publish_to = publish_to.replace(tzinfo=timezone.utc)

        logger.info(
            "Fetching WINDFOR from %s to %s in %d-day chunks",
            publish_from.isoformat(),
            publish_to.isoformat(),
            chunk_days,
        )

        for chunk_start, chunk_end in self._chunk_datetimes(publish_from, publish_to, chunk_days=chunk_days):
            params = {
                "publishDateTimeFrom": chunk_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "publishDateTimeTo": chunk_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            logger.info(
                "Fetching WINDFOR chunk: %s to %s",
                params["publishDateTimeFrom"],
                params["publishDateTimeTo"],
            )
            data = self._get_json("datasets/WINDFOR/stream", params=params)
            logger.info("Retrieved %d WINDFOR records for chunk", len(data))
            all_records.extend(data)

        logger.info("Completed WINDFOR fetch. Total forecast records retrieved: %d", len(all_records))
        return all_records

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import time

import pandas as pd
import requests


BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
SECONDS_PER_DAY = 24 * 60 * 60


def iso_to_unix(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return int(dt.timestamp())


def unix_to_utc(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def resolve_series_ticker(event_ticker):
    response = requests.get(f"{BASE_URL}/events/{event_ticker}", timeout=30)
    response.raise_for_status()
    event = response.json().get("event", {})
    series_ticker = event.get("series_ticker")
    return series_ticker


def fetch_live_candles(
    series_ticker,
    market_ticker,
    start_ts,
    end_ts,
    period_interval,
    include_latest_before_start,
):
    url = f"{BASE_URL}/series/{series_ticker}/markets/{market_ticker}/candlesticks"
    params = {
        "start_ts": start_ts,
        "end_ts": end_ts,
        "period_interval": period_interval,
        "include_latest_before_start": str(include_latest_before_start).lower(),
    }
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def fetch_historical_candles(
    market_ticker,
    start_ts,
    end_ts,
    period_interval,
):
    url = f"{BASE_URL}/historical/markets/{market_ticker}/candlesticks"
    params = {
        "start_ts": start_ts,
        "end_ts": end_ts,
        "period_interval": period_interval,
    }
    max_attempts = 6

    for attempt in range(1, max_attempts + 1):
        response = requests.get(url, params=params, timeout=30)
        if response.status_code != 429:
            response.raise_for_status()
            return response.json()
        retry_after = response.headers.get("Retry-After")
        wait_seconds = int(retry_after) if retry_after and retry_after.isdigit() else min(2 ** attempt, 60)
        print(
            f"Rate limited on historical candles for {market_ticker} "
            f"({start_ts} to {end_ts}). Waiting {wait_seconds}s before retry {attempt}/{max_attempts}..."
        )
        time.sleep(wait_seconds)

    response.raise_for_status()
    return response.json()


def chunked_historical_fetch(
    market_ticker,
    start_ts,
    end_ts,
    period_interval,
):
    chunk_days = 30 if period_interval == 60 else 180
    chunk_seconds = chunk_days * SECONDS_PER_DAY

    all_candles: list[dict] = []
    current_start = start_ts
    while current_start <= end_ts:
        current_end = min(current_start + chunk_seconds - 1, end_ts)
        payload = fetch_historical_candles(
            market_ticker=market_ticker,
            start_ts=current_start,
            end_ts=current_end,
            period_interval=period_interval,
        )
        all_candles.extend(payload.get("candlesticks", []))
        current_start = current_end + 1

    unique = {}
    for candle in all_candles:
        unique[candle["end_period_ts"]] = candle

    return {
        "ticker": market_ticker,
        "candlesticks": [unique[ts] for ts in sorted(unique)],
    }


def normalize_candles(payload, market_ticker, event_id):
    rows = []
    for candle in payload.get("candlesticks", []):
        price = candle.get("price", {})
        volume = candle.get("volume_fp", candle.get("volume"))
        open_interest = candle.get("open_interest_fp", candle.get("open_interest"))
        timestamp = candle.get("end_period_ts")

        rows.append(
            {
                "timestamp": unix_to_utc(timestamp),
                "market_prob": price.get("close_dollars", price.get("close")),
                "market_open": price.get("open_dollars", price.get("open")),
                "market_high": price.get("high_dollars", price.get("high")),
                "market_low": price.get("low_dollars", price.get("low")),
                "market_mean": price.get("mean_dollars", price.get("mean")),
                "market_previous": price.get("previous_dollars", price.get("previous")),
                "market_volume": volume,
                "open_interest": open_interest,
                "market_ticker": market_ticker,
                "event_id": event_id or market_ticker,
            }
        )

    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame

    numeric_cols = [
        "market_prob",
        "market_open",
        "market_high",
        "market_low",
        "market_mean",
        "market_previous",
        "market_volume",
        "open_interest",
    ]
    for col in numeric_cols:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")

    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    return frame.sort_values("timestamp").reset_index(drop=True)


def main():
    parser = argparse.ArgumentParser(
        description="download Kalshi candlesticks and save notebook-ready market_data.csv."
    )
    parser.add_argument("--market-ticker", required=True, help="Kalshi market ticker.")
    parser.add_argument("--series-ticker", help="Required for live endpoint")
    parser.add_argument("--event-ticker", help="OPTIONAL! helper for resolving series ticker when on live requests")
    parser.add_argument(
        "--endpoint",
        choices=["live", "historical"],
        default="live",
        help="Use live candles or historical archived candles",
    )
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument(
        "--period-interval",
        type=int,
        default=60,
        choices=[1, 60, 1440],
        help="Candle size in minutes",
    )
    parser.add_argument(
        "--include-latest-before-start",
        action="store_true",
        help="Live endpoint only, include a synthetic latest candle before start.",
    )
    parser.add_argument("--event-id", help="Optional event_id column override for the notebook.")
    parser.add_argument(
        "--out",
        default="data/raw/market_data.csv",
        help="Output CSV path.",
    )
    args = parser.parse_args()
    start_ts = iso_to_unix(args.start)
    end_ts = iso_to_unix(args.end)

    if args.endpoint == "live":
        series_ticker = args.series_ticker
        if not series_ticker:
            series_ticker = resolve_series_ticker(args.event_ticker)
        payload = fetch_live_candles(
            series_ticker=series_ticker,
            market_ticker=args.market_ticker,
            start_ts=start_ts,
            end_ts=end_ts,
            period_interval=args.period_interval,
            include_latest_before_start=args.include_latest_before_start,
        )
    else:
        payload = chunked_historical_fetch(
            market_ticker=args.market_ticker,
            start_ts=start_ts,
            end_ts=end_ts,
            period_interval=args.period_interval,
        )

    frame = normalize_candles(payload, market_ticker=args.market_ticker, event_id=args.event_id)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out_path, index=False)

    print(f"Saved {len(frame)} rows to {out_path}")
    if not frame.empty:
        print(frame.head(10).to_string(index=False))


if __name__ == "__main__":
    main()

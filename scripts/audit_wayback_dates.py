#!/usr/bin/env python3
"""Resolve remaining links to their earliest verified Wayback capture date."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import threading
import time
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import requests


INPUT = Path("io_links.md")
REPORT = Path("scratch/wayback-date-audit.json")
CACHE = Path("tmp/wayback-availability-cache")
ENDPOINT = "https://archive.org/wayback/available"
BEFORE = date(2026, 7, 28)
throttle_lock = threading.Lock()
last_request = 0.0


def cache_path(url: str) -> Path:
    return CACHE / f"{hashlib.sha256(url.encode()).hexdigest()}.json"


def throttled_get(url: str) -> requests.Response:
    global last_request
    with throttle_lock:
        delay = 0.8 - (time.monotonic() - last_request)
        if delay > 0:
            time.sleep(delay)
        last_request = time.monotonic()
    return requests.get(
        ENDPOINT,
        params={"url": url, "timestamp": "19800101"},
        headers={"User-Agent": "io-links-date-audit/1.0"},
        timeout=30,
    )


def inspect(url: str) -> dict:
    path = cache_path(url)
    payload = None
    if path.exists():
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            if cached.get("_http_status") == 200:
                payload = cached
        except (OSError, ValueError):
            pass
    if payload is None:
        errors = []
        for attempt in range(4):
            try:
                response = throttled_get(url)
                if response.status_code == 200:
                    payload = response.json()
                    payload["_http_status"] = 200
                    path.write_text(
                        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
                        encoding="utf-8",
                        newline="\n",
                    )
                    break
                errors.append(f"HTTP {response.status_code}")
                if response.status_code in {429, 502, 503, 504}:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                break
            except (requests.RequestException, ValueError) as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
                time.sleep(1.5 * (attempt + 1))
        if payload is None:
            return {
                "url": url,
                "status": None,
                "date": None,
                "unresolved_reason": "; ".join(errors),
            }

    snapshot = (payload.get("archived_snapshots") or {}).get("closest") or {}
    timestamp = str(snapshot.get("timestamp") or "")
    if (
        snapshot.get("available")
        and snapshot.get("status") == "200"
        and len(timestamp) >= 8
        and timestamp[:8].isdigit()
    ):
        try:
            value = date(
                int(timestamp[:4]), int(timestamp[4:6]), int(timestamp[6:8])
            )
        except ValueError:
            pass
        else:
            if value < BEFORE:
                return {
                    "url": url,
                    "status": "archived",
                    "date": value.isoformat(),
                    "source": snapshot.get("url"),
                    "evidence": (
                        "Wayback Availability API capture closest to 1980-01-01; "
                        "therefore the earliest available capture."
                    ),
                    "timestamp": timestamp,
                }
    return {
        "url": url,
        "status": None,
        "date": None,
        "source": snapshot.get("url"),
        "unresolved_reason": "No successful pre-index Wayback capture found.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument(
        "--host",
        action="append",
        default=[],
        help="Only audit this hostname; may be supplied more than once.",
    )
    parser.add_argument(
        "--cache-only",
        action="store_true",
        help="Report cached successful captures without making network requests.",
    )
    args = parser.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    targets = []
    for line in INPUT.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) != 3 or fields[1] != "indexed":
            continue
        parsed = urlparse(fields[0])
        if args.host and (parsed.hostname or "").lower() not in {
            host.lower() for host in args.host
        }:
            continue
        if parsed.scheme in {"http", "https"}:
            path = cache_path(fields[0])
            if args.cache_only and not path.exists():
                continue
            if path.exists():
                try:
                    cached = json.loads(path.read_text(encoding="utf-8"))
                    snapshot = (
                        (cached.get("archived_snapshots") or {}).get("closest") or {}
                    )
                    if not snapshot.get("available"):
                        continue
                except (OSError, ValueError):
                    pass
            targets.append(fields[0])
    targets.sort(key=lambda url: (not cache_path(url).exists(), url))
    if args.limit > 0:
        targets = targets[: args.limit]
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(inspect, url): url for url in targets}
        for count, future in enumerate(concurrent.futures.as_completed(futures), 1):
            results.append(future.result())
            if count % 100 == 0 or count == len(futures):
                resolved = sum(bool(item.get("date")) for item in results)
                print(f"{count}/{len(futures)} checked; {resolved} archived", flush=True)
    payload = {
        "target_count": len(results),
        "resolved_count": sum(bool(item.get("date")) for item in results),
        "unresolved_count": sum(not item.get("date") for item in results),
        "results": sorted(results, key=lambda item: item["url"]),
    }
    args.report.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print({key: value for key, value in payload.items() if key.endswith("_count")})


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Find the earliest successful Common Crawl capture of indexed links."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import time
from pathlib import Path
from urllib.parse import urlparse

import requests


INPUT = Path("io_links.md")
CACHE = Path("tmp/commoncrawl-date-cache")
REPORT = Path("scratch/commoncrawl-date-audit.json")
COLLECTIONS = "https://index.commoncrawl.org/collinfo.json"


def cache_path(url: str) -> Path:
    return CACHE / f"{hashlib.sha256(url.encode()).hexdigest()}.json"


def query_collection(endpoint: str, url: str) -> list[dict]:
    for attempt in range(3):
        try:
            response = requests.get(
                endpoint,
                params={
                    "url": url,
                    "output": "json",
                    "filter": "status:200",
                },
                headers={"User-Agent": "io-links-date-audit/1.0"},
                timeout=30,
            )
            if response.status_code == 404:
                return []
            if response.status_code == 200:
                return [
                    json.loads(line)
                    for line in response.text.splitlines()
                    if line.strip()
                ]
            if response.status_code not in {429, 502, 503, 504}:
                return []
        except (requests.RequestException, ValueError):
            pass
        time.sleep(1.5 * (attempt + 1))
    return []


def inspect(url: str, collections: list[dict], cache_only: bool) -> dict:
    path = cache_path(url)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    if cache_only:
        return {"url": url, "date": None, "unresolved_reason": "Not cached."}

    for collection in collections:
        records = query_collection(collection["cdx-api"], url)
        if not records:
            continue
        record = min(records, key=lambda item: str(item.get("timestamp") or "9"))
        timestamp = str(record.get("timestamp") or "")
        if len(timestamp) >= 8 and timestamp[:8].isdigit():
            result = {
                "url": url,
                "status": "archived",
                "date": (
                    f"{timestamp[:4]}-{timestamp[4:6]}-{timestamp[6:8]}"
                ),
                "timestamp": timestamp,
                "collection": collection["id"],
                "source": collection["cdx-api"],
                "evidence": (
                    "Earliest successful exact-URL capture in the available "
                    "Common Crawl indexes."
                ),
            }
            path.write_text(
                json.dumps(result, indent=2, ensure_ascii=True) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            return result
    result = {
        "url": url,
        "date": None,
        "unresolved_reason": "No successful exact-URL Common Crawl capture.",
    }
    path.write_text(
        json.dumps(result, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--cache-only", action="store_true")
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--host", action="append", default=[])
    args = parser.parse_args()

    CACHE.mkdir(parents=True, exist_ok=True)
    response = requests.get(
        COLLECTIONS,
        headers={"User-Agent": "io-links-date-audit/1.0"},
        timeout=30,
    )
    response.raise_for_status()
    collections = sorted(response.json(), key=lambda item: item["from"])
    allowed_hosts = {host.casefold() for host in args.host}
    targets = []
    for line in INPUT.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) != 3 or fields[1] != "indexed":
            continue
        parsed = urlparse(fields[0])
        if parsed.scheme not in {"http", "https"}:
            continue
        if allowed_hosts and (parsed.hostname or "").casefold() not in allowed_hosts:
            continue
        targets.append(fields[0])
    targets.sort(key=lambda url: (cache_path(url).exists(), url))
    if args.limit:
        targets = targets[: args.limit]

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(inspect, url, collections, args.cache_only): url
            for url in targets
        }
        for count, future in enumerate(concurrent.futures.as_completed(futures), 1):
            results.append(future.result())
            if count % 10 == 0 or count == len(futures):
                resolved = sum(bool(item.get("date")) for item in results)
                print(f"{count}/{len(futures)} checked; {resolved} archived", flush=True)

    payload = {
        "target_count": len(results),
        "resolved_count": sum(bool(item.get("date")) for item in results),
        "unresolved_count": sum(not item.get("date") for item in results),
        "results": sorted(results, key=lambda item: item["url"]),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print({key: value for key, value in payload.items() if key.endswith("_count")})


if __name__ == "__main__":
    main()

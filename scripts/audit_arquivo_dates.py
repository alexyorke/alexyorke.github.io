#!/usr/bin/env python3
"""Find earliest exact-URL captures in the Arquivo.pt web archive."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

import requests


INPUT = Path("io_links.md")
CACHE = Path("tmp/arquivo-date-cache")
REPORT = Path("scratch/arquivo-date-audit.json")
ENDPOINT = "https://arquivo.pt/textsearch"


def cache_path(url: str) -> Path:
    return CACHE / f"{hashlib.sha256(url.encode()).hexdigest()}.json"


def inspect(url: str) -> dict:
    path = cache_path(url)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    try:
        response = requests.get(
            ENDPOINT,
            params={"versionHistory": url, "maxItems": 50},
            headers={"User-Agent": "io-links-date-audit/1.0"},
            timeout=30,
        )
        response.raise_for_status()
        items = response.json().get("response_items") or []
    except (requests.RequestException, ValueError) as exc:
        return {
            "url": url,
            "date": None,
            "unresolved_reason": f"{type(exc).__name__}: {exc}",
        }

    exact = [
        item
        for item in items
        if str(item.get("originalURL") or "").rstrip("/") == url.rstrip("/")
    ]
    candidates = exact or items
    timestamps = [
        str(item.get("tstamp") or item.get("timestamp") or "")
        for item in candidates
    ]
    timestamps = [
        value for value in timestamps if len(value) >= 8 and value[:8].isdigit()
    ]
    if timestamps:
        timestamp = min(timestamps)
        result = {
            "url": url,
            "status": "archived",
            "date": f"{timestamp[:4]}-{timestamp[4:6]}-{timestamp[6:8]}",
            "timestamp": timestamp,
            "source": response.url,
            "evidence": "Earliest exact-URL capture returned by Arquivo.pt.",
        }
    else:
        result = {
            "url": url,
            "date": None,
            "source": response.url,
            "unresolved_reason": "No exact-URL Arquivo.pt capture.",
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
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--host", action="append", default=[])
    parser.add_argument("--report", type=Path, default=REPORT)
    args = parser.parse_args()

    CACHE.mkdir(parents=True, exist_ok=True)
    allowed_hosts = {value.casefold() for value in args.host}
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
        for count, result in enumerate(pool.map(inspect, targets), 1):
            results.append(result)
            if count % 25 == 0 or count == len(targets):
                resolved = sum(bool(item.get("date")) for item in results)
                print(f"{count}/{len(targets)} checked; {resolved} archived", flush=True)

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

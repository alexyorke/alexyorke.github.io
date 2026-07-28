#!/usr/bin/env python3
"""Resolve versioned Rocq package pages from their displayed publication dates."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser


def inspect(url: str) -> dict:
    item = {"url": url, "status": None, "date": None, "source": "rocq-package-page"}
    try:
        response = requests.get(
            url, headers={"User-Agent": "io-links-date-audit/1.0"}, timeout=30
        )
        item["http_status"] = response.status_code
        if not response.ok:
            return item
        soup = BeautifulSoup(response.content, "html.parser")
        heading = soup.find(
            lambda tag: tag.name in {"h1", "h2", "h3"}
            and "Published:" in tag.get_text(" ", strip=True)
        )
        if heading:
            raw = heading.get_text(" ", strip=True).replace("Published:", "").strip()
            value = date_parser.parse(raw, fuzzy=False).date().isoformat()
            item.update(
                status="published",
                date=value,
                evidence=f"Published: {raw}",
            )
    except (requests.RequestException, OverflowError, ValueError) as exc:
        item["error"] = f"{type(exc).__name__}: {exc}"
    return item


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, default=Path("io_links.md"))
    parser.add_argument(
        "--report", type=Path, default=Path("scratch/rocq-package-audit.json")
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    lines = args.file.read_text(encoding="utf-8").splitlines()
    urls = []
    for line in lines:
        parts = line.split("\t")
        if len(parts) != 3 or parts[1] != "indexed":
            continue
        parsed = urlparse(parts[0])
        if parsed.netloc.lower() != "rocq-prover.org":
            continue
        if re.fullmatch(r"/p/[^/]+/\d+(?:\.\d+)+/?", parsed.path):
            urls.append(parts[0])
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(inspect, urls))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(results, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    if args.apply:
        resolved = {item["url"]: item for item in results if item.get("date")}
        changed = 0
        for index, line in enumerate(lines):
            parts = line.split("\t")
            item = resolved.get(parts[0]) if len(parts) == 3 else None
            if len(parts) == 3 and parts[1] == "indexed" and item:
                lines[index] = f"{parts[0]}\t{item['status']}\t{item['date']}"
                changed += 1
        args.file.write_text(
            "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
        )
        print(f"Updated {changed}/{len(urls)} rows", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

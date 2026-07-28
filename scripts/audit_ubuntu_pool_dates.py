#!/usr/bin/env python3
"""Resolve Ubuntu pool directory URLs from their earliest package timestamp."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests


TIMESTAMP_RE = re.compile(
    r'<a href="(?P<file>[^"]+)">.*?</a>\s+'
    r'(?P<stamp>\d{2}-[A-Z][a-z]{2}-\d{4} \d{2}:\d{2})',
    re.S,
)
TIMESTAMP_ISO_RE = re.compile(
    r'<a href="(?P<file>[^"]+)">.*?</a>.*?'
    r'(?P<stamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2})',
    re.S,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, default=Path("io_links.md"))
    parser.add_argument(
        "--report", type=Path, default=Path("scratch/ubuntu-pool-date-audit.json")
    )
    args = parser.parse_args()

    targets = []
    for line in args.file.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) != 3 or parts[1] != "indexed":
            continue
        if urlparse(parts[0]).netloc.lower().endswith("archive.ubuntu.com"):
            targets.append(parts[0])

    session = requests.Session()
    results = []
    for url in targets:
        response = session.get(url, timeout=30)
        matches = [
            (name, datetime.strptime(stamp, "%d-%b-%Y %H:%M"))
            for name, stamp in TIMESTAMP_RE.findall(response.text)
            if name != "../"
        ]
        matches.extend(
            (name, datetime.strptime(stamp, "%Y-%m-%d %H:%M"))
            for name, stamp in TIMESTAMP_ISO_RE.findall(response.text)
            if name != "../"
        )
        item = {
            "url": url,
            "source": "ubuntu-pool-directory",
            "http_status": response.status_code,
            "status": None,
            "date": None,
        }
        if response.ok and matches:
            filename, timestamp = min(matches, key=lambda pair: pair[1])
            item.update(
                status="uploaded",
                date=timestamp.date().isoformat(),
                evidence=f"{filename} {timestamp:%d-%b-%Y %H:%M}",
            )
        results.append(item)

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(results, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"Resolved {sum(bool(item['date']) for item in results)}/{len(results)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

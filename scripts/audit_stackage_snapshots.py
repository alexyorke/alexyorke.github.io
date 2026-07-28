#!/usr/bin/env python3
"""Resolve Stackage LTS snapshot dates from their first Git commit."""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import requests


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, default=Path("io_links.md"))
    parser.add_argument(
        "--report", type=Path, default=Path("scratch/stackage-snapshot-audit.json")
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    lines = args.file.read_text(encoding="utf-8").splitlines()
    targets: dict[str, tuple[int, int]] = {}
    for line in lines:
        parts = line.split("\t")
        if len(parts) != 3 or parts[1] != "indexed":
            continue
        parsed = urlparse(parts[0])
        if parsed.netloc.lower() != "www.stackage.org":
            continue
        match = re.fullmatch(r"/lts-(\d+)(?:\.(\d+))?/?", parsed.path)
        if match:
            targets[parts[0]] = (int(match.group(1)), int(match.group(2) or 0))

    session = requests.Session()
    results = []
    for count, (url, (major, minor)) in enumerate(targets.items(), 1):
        if major <= 14:
            repository = "commercialhaskell/lts-haskell"
            path = f"lts-{major}.{minor}.yaml"
        else:
            repository = "commercialhaskell/stackage-snapshots"
            path = f"lts/{major}/{minor}.yaml"
        response = session.get(
            f"https://api.github.com/repos/{repository}/commits",
            params={"path": path, "per_page": 100},
            headers={"User-Agent": "io-links-date-audit/1.0"},
            timeout=30,
        )
        item = {
            "url": url,
            "status": None,
            "date": None,
            "source": "github-commit-history",
            "repository": repository,
            "path": path,
            "http_status": response.status_code,
        }
        if response.status_code == 200:
            commits = response.json()
            if isinstance(commits, list) and commits:
                oldest = commits[-1]
                timestamp = oldest["commit"]["author"]["date"]
                item.update(
                    status="published",
                    date=timestamp[:10],
                    evidence=f"first commit {oldest['sha']}",
                )
        results.append(item)
        print(
            f"{count}/{len(targets)} checked; "
            f"{sum(bool(x.get('date')) for x in results)} resolved",
            flush=True,
        )
        time.sleep(0.25)

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
        print(f"Updated {changed} rows", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

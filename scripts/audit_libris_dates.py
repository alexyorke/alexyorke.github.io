#!/usr/bin/env python3
"""Resolve Libris catalog URLs from official publication metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

import requests


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, default=Path("io_links.md"))
    parser.add_argument(
        "--report", type=Path, default=Path("scratch/libris-date-audit.json")
    )
    args = parser.parse_args()

    targets = []
    for line in args.file.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if (
            len(parts) == 3
            and parts[1] == "indexed"
            and urlparse(parts[0]).netloc.lower() == "libris.kb.se"
        ):
            targets.append(parts[0])

    session = requests.Session()
    results = []
    for url in targets:
        response = session.get(
            url, headers={"Accept": "application/ld+json"}, timeout=30
        )
        item = {
            "url": url,
            "source": "libris-jsonld",
            "http_status": response.status_code,
            "status": None,
            "date": None,
        }
        if response.ok:
            graph = response.json().get("@graph", [])
            resource = next((node for node in graph if node.get("publication")), None)
            publications = resource.get("publication", []) if resource else []
            years = [
                value
                for publication in publications
                if (value := publication.get("year"))
            ]
            if years:
                item.update(
                    status="publication",
                    date=min(years),
                    evidence=publications,
                )
        results.append(item)

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(results, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"Resolved {sum(bool(item['date']) for item in results)}/{len(results)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

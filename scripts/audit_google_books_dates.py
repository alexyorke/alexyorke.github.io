#!/usr/bin/env python3
"""Resolve Google Books URLs from Google Books volume metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, default=Path("io_links.md"))
    parser.add_argument(
        "--report", type=Path, default=Path("scratch/google-books-date-audit.json")
    )
    args = parser.parse_args()

    targets = {}
    for line in args.file.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) != 3 or parts[1] != "indexed":
            continue
        parsed = urlparse(parts[0])
        if not parsed.netloc.lower().startswith("books.google."):
            continue
        volume_id = (parse_qs(parsed.query).get("id") or [None])[0]
        if not volume_id and "/books/about/" in parsed.path:
            volume_id = (parse_qs(parsed.query).get("id") or [None])[0]
        if volume_id:
            targets[parts[0]] = volume_id

    session = requests.Session()
    metadata = {}
    for volume_id in sorted(set(targets.values())):
        api_url = f"https://www.googleapis.com/books/v1/volumes/{volume_id}"
        response = session.get(api_url, timeout=30)
        info = response.json().get("volumeInfo", {}) if response.ok else {}
        metadata[volume_id] = {
            "source": api_url,
            "date": info.get("publishedDate"),
            "title": info.get("title"),
            "publisher": info.get("publisher"),
            "http_status": response.status_code,
        }

    results = []
    for url, volume_id in targets.items():
        info = metadata[volume_id]
        results.append(
            {
                "url": url,
                "status": "publication" if info["date"] else None,
                "date": info["date"],
                "source": info["source"],
                "evidence": {
                    "title": info["title"],
                    "publisher": info["publisher"],
                    "http_status": info["http_status"],
                },
            }
        )

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

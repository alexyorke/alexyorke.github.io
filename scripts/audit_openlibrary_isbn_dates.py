#!/usr/bin/env python3
"""Resolve ISBN-bearing book URLs from Open Library edition metadata."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests
from dateutil import parser as date_parser


ISBN_RE = re.compile(r"(97[89]\d{10})")


def normalize_date(value: str | None) -> str | None:
    if not value:
        return None
    if re.fullmatch(r"\d{4}", value):
        return value
    try:
        return date_parser.parse(value).date().isoformat()
    except (OverflowError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, default=Path("io_links.md"))
    parser.add_argument(
        "--report", type=Path, default=Path("scratch/openlibrary-isbn-date-audit.json")
    )
    args = parser.parse_args()

    targets = {}
    for line in args.file.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) != 3 or parts[1] != "indexed":
            continue
        match = ISBN_RE.search(unquote(urlparse(parts[0]).path))
        if match:
            targets[parts[0]] = match.group(1)

    keys = [f"ISBN:{isbn}" for isbn in sorted(set(targets.values()))]
    response = requests.get(
        "https://openlibrary.org/api/books",
        params={"bibkeys": ",".join(keys), "jscmd": "data", "format": "json"},
        timeout=60,
    )
    payload = response.json() if response.ok else {}
    results = []
    for url, isbn in targets.items():
        info = payload.get(f"ISBN:{isbn}", {})
        date = normalize_date(info.get("publish_date"))
        results.append(
            {
                "url": url,
                "status": "publication" if date else None,
                "date": date,
                "source": info.get("url") or "https://openlibrary.org/api/books",
                "evidence": {
                    "isbn": isbn,
                    "title": info.get("title"),
                    "publisher": info.get("publishers"),
                    "raw_publish_date": info.get("publish_date"),
                    "http_status": response.status_code,
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

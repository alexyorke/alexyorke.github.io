#!/usr/bin/env python3
"""Resolve Nottingham repository entities from DSpace item metadata."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse

import requests


ENTITY_RE = re.compile(r"/entities/publication/([0-9a-f-]+)$", re.I)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, default=Path("io_links.md"))
    parser.add_argument(
        "--report", type=Path, default=Path("scratch/nottingham-date-audit.json")
    )
    args = parser.parse_args()

    targets = {}
    for line in args.file.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) != 3 or parts[1] != "indexed":
            continue
        parsed = urlparse(parts[0])
        if parsed.netloc.lower() != "repository.nottingham.ac.uk":
            continue
        match = ENTITY_RE.fullmatch(parsed.path)
        if match:
            targets[parts[0]] = match.group(1)

    session = requests.Session()
    results = []
    for url, item_id in targets.items():
        api_url = (
            "https://repository.nottingham.ac.uk/server/api/core/items/" + item_id
        )
        response = session.get(api_url, timeout=30)
        payload = response.json() if response.ok else {}
        values = payload.get("metadata", {}).get("dc.date.issued", [])
        date = values[0].get("value") if values else None
        results.append(
            {
                "url": url,
                "status": "publication" if date else None,
                "date": date,
                "source": api_url,
                "evidence": {
                    "title": payload.get("name"),
                    "dc.date.issued": date,
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

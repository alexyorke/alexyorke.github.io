#!/usr/bin/env python3
"""Resolve content.openalex.org work files from OpenAlex work metadata."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse

import requests


WORK_RE = re.compile(r"/works/(W\d+)\.(?:pdf|grobid-xml)$")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, default=Path("io_links.md"))
    parser.add_argument(
        "--report", type=Path, default=Path("scratch/openalex-content-date-audit.json")
    )
    args = parser.parse_args()

    targets = {}
    for line in args.file.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) != 3 or parts[1] != "indexed":
            continue
        parsed = urlparse(parts[0])
        if parsed.netloc.lower() != "content.openalex.org":
            continue
        match = WORK_RE.fullmatch(parsed.path)
        if match:
            targets[parts[0]] = match.group(1)

    session = requests.Session()
    metadata = {}
    for work_id in sorted(set(targets.values())):
        response = session.get(
            f"https://api.openalex.org/works/{work_id}",
            params={"mailto": "date-audit@example.com"},
            timeout=30,
        )
        payload = response.json() if response.ok else {}
        metadata[work_id] = {
            "http_status": response.status_code,
            "date": payload.get("publication_date"),
            "title": payload.get("title"),
            "doi": payload.get("doi"),
        }

    results = []
    for url, work_id in targets.items():
        info = metadata[work_id]
        results.append(
            {
                "url": url,
                "status": "publication" if info["date"] else None,
                "date": info["date"],
                "source": f"https://api.openalex.org/works/{work_id}",
                "evidence": {
                    "title": info["title"],
                    "doi": info["doi"],
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

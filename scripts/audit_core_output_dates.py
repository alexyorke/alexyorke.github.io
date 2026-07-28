#!/usr/bin/env python3
"""Resolve CORE file URLs from CORE output metadata."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse

import requests


OUTPUT_RE = re.compile(r"/download/(?:pdf/)?(\d+)\.pdf$")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, default=Path("io_links.md"))
    parser.add_argument(
        "--report", type=Path, default=Path("scratch/core-output-date-audit.json")
    )
    args = parser.parse_args()

    targets = {}
    for line in args.file.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) != 3 or parts[1] != "indexed":
            continue
        parsed = urlparse(parts[0])
        if parsed.netloc.lower() != "files01.core.ac.uk":
            continue
        match = OUTPUT_RE.fullmatch(parsed.path)
        if match:
            targets[parts[0]] = match.group(1)

    session = requests.Session()
    results = []
    for url, output_id in targets.items():
        api_url = f"https://api.core.ac.uk/v3/outputs/{output_id}"
        response = session.get(api_url, timeout=30)
        payload = response.json() if response.ok else {}
        published = payload.get("publishedDate")
        date = published[:10] if published else str(payload.get("yearPublished") or "") or None
        results.append(
            {
                "url": url,
                "status": "publication" if date else None,
                "date": date,
                "source": api_url,
                "evidence": {
                    "title": payload.get("title"),
                    "authors": payload.get("authors"),
                    "document_type": payload.get("documentType"),
                    "source_urls": payload.get("sourceFulltextUrls"),
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

#!/usr/bin/env python3
"""Resolve Oxford ORA file URLs from their parent object's citation metadata."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse

import requests


DATE_RE = re.compile(
    r'<meta\s+name="citation_publication_date"\s+content="([^"]+)"', re.I
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, default=Path("io_links.md"))
    parser.add_argument("--report", type=Path, default=Path("scratch/ora-date-audit.json"))
    args = parser.parse_args()

    targets = []
    for line in args.file.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if (
            len(parts) == 3
            and parts[1] == "indexed"
            and urlparse(parts[0]).netloc.lower() == "ora.ox.ac.uk"
        ):
            targets.append(parts[0])

    session = requests.Session()
    results = []
    for url in targets:
        object_url = url.split("/files/", 1)[0]
        response = session.get(
            object_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30
        )
        match = DATE_RE.search(response.text) if response.ok else None
        date = match.group(1) if match else None
        results.append(
            {
                "url": url,
                "status": "publication" if date else None,
                "date": date,
                "source": object_url,
                "evidence": (
                    f"Parent object citation_publication_date={date}; "
                    f"HTTP {response.status_code}"
                ),
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

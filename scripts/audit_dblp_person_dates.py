#!/usr/bin/env python3
"""Resolve DBLP person pages from their official record modification date."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests


PERSON_RE = re.compile(r"/pid/(.+?)(?:\.html)?/?$")
MDATE_RE = re.compile(r'<person\b[^>]*\bmdate="(\d{4}-\d{2}-\d{2})"')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, default=Path("io_links.md"))
    parser.add_argument(
        "--report", type=Path, default=Path("scratch/dblp-person-date-audit.json")
    )
    args = parser.parse_args()

    targets = {}
    for line in args.file.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) != 3 or parts[1] != "indexed":
            continue
        parsed = urlparse(parts[0])
        if parsed.netloc.lower() != "dblp.org":
            continue
        match = PERSON_RE.fullmatch(unquote(parsed.path))
        if match:
            targets[parts[0]] = match.group(1)

    session = requests.Session()
    metadata = {}
    for pid in sorted(set(targets.values())):
        xml_url = f"https://dblp.org/pid/{pid}.xml"
        try:
            response = session.get(xml_url, timeout=20)
            match = MDATE_RE.search(response.text) if response.ok else None
            metadata[pid] = {
                "source": xml_url,
                "date": match.group(1) if match else None,
                "http_status": response.status_code,
            }
        except requests.RequestException as error:
            metadata[pid] = {
                "source": xml_url,
                "date": None,
                "http_status": None,
                "error": f"{type(error).__name__}: {error}",
            }

    results = []
    for url, pid in targets.items():
        info = metadata[pid]
        results.append(
            {
                "url": url,
                "status": "modified" if info["date"] else None,
                "date": info["date"],
                "source": info["source"],
                "evidence": f"DBLP person record mdate; HTTP {info['http_status']}",
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

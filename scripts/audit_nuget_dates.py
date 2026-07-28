#!/usr/bin/env python3
"""Resolve NuGet package-version pages from official registration metadata."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests


PACKAGE_RE = re.compile(r"/packages/([^/]+)/([^/]+)/?$", re.I)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, default=Path("io_links.md"))
    parser.add_argument(
        "--report", type=Path, default=Path("scratch/nuget-date-audit.json")
    )
    args = parser.parse_args()

    targets = {}
    for line in args.file.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) != 3 or parts[1] != "indexed":
            continue
        parsed = urlparse(parts[0])
        if not parsed.netloc.lower().endswith("nuget.org"):
            continue
        match = PACKAGE_RE.fullmatch(unquote(parsed.path))
        if match:
            targets[parts[0]] = match.groups()

    session = requests.Session()
    results = []
    for url, (package, version) in targets.items():
        api_url = (
            "https://api.nuget.org/v3/registration5-gz-semver2/"
            f"{package.lower()}/{version.lower()}.json"
        )
        response = session.get(api_url, timeout=30)
        payload = response.json() if response.ok else {}
        published = payload.get("published")
        results.append(
            {
                "url": url,
                "status": "published" if published else None,
                "date": published[:10] if published else None,
                "source": api_url,
                "evidence": {
                    "package_content": payload.get("packageContent"),
                    "catalog_entry": payload.get("catalogEntry"),
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

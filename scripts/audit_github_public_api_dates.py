#!/usr/bin/env python3
"""Resolve GitHub repository and gist URLs through the public GitHub API."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests


GIST_ID_RE = re.compile(r"[0-9a-f]{5,40}", re.I)


def endpoint(url: str) -> str | None:
    parsed = urlparse(url)
    parts = [unquote(part) for part in parsed.path.strip("/").split("/") if part]
    host = parsed.netloc.lower()
    if host == "github.com" and len(parts) == 2:
        return f"https://api.github.com/repos/{parts[0]}/{parts[1]}"
    if host == "gist.github.com" and len(parts) >= 2 and GIST_ID_RE.fullmatch(parts[1]):
        return f"https://api.github.com/gists/{parts[1]}"
    if (
        host == "gist.githubusercontent.com"
        and len(parts) >= 2
        and GIST_ID_RE.fullmatch(parts[1])
    ):
        return f"https://api.github.com/gists/{parts[1]}"
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, default=Path("io_links.md"))
    parser.add_argument(
        "--report", type=Path, default=Path("scratch/github-public-api-date-audit.json")
    )
    args = parser.parse_args()

    targets = {}
    for line in args.file.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[1] == "indexed":
            if api_url := endpoint(parts[0]):
                targets[parts[0]] = api_url

    session = requests.Session()
    session.headers["Accept"] = "application/vnd.github+json"
    results = []
    for url, api_url in targets.items():
        response = session.get(api_url, timeout=30)
        payload = response.json() if response.ok else {}
        created = payload.get("created_at")
        results.append(
            {
                "url": url,
                "status": "created" if created else None,
                "date": created[:10] if created else None,
                "source": api_url,
                "evidence": {
                    "name": payload.get("full_name") or payload.get("description"),
                    "html_url": payload.get("html_url"),
                    "created_at": created,
                    "http_status": response.status_code,
                    "rate_remaining": response.headers.get("X-RateLimit-Remaining"),
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

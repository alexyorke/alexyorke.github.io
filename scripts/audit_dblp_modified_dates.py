#!/usr/bin/env python3
"""Resolve mutable DBLP pages from their explicit modification metadata."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import requests


INPUT = Path("io_links.md")
REPORT = Path("scratch/dblp-modified-dates-audit.json")


DBLP_MIRRORS = ("dblp.uni-trier.de", "dblp.dagstuhl.de", "dblp.org")


def audit(url: str) -> dict:
    parsed = urlparse(url)
    if parsed.path.startswith("/pid/"):
        path = re.sub(r"\.html$", "", parsed.path)
        failures = []
        for host in DBLP_MIRRORS:
            source = f"https://{host}{path}.xml"
            time.sleep(0.75)
            try:
                response = requests.get(
                    source,
                    headers={"User-Agent": "io-links-date-audit/1.0"},
                    timeout=30,
                )
            except requests.RequestException as exc:
                failures.append(f"{host}: {type(exc).__name__}")
                continue
            match = re.search(
                r"<person\b[^>]*\bmdate=\"(\d{4}-\d{2}-\d{2})\"", response.text
            )
            if match:
                return {
                    "url": url,
                    "status": "modified",
                    "date": match.group(1),
                    "evidence": "DBLP person record mdate attribute.",
                    "source": source,
                }
            failures.append(f"{host}: HTTP {response.status_code}")
        return {
            "url": url,
            "unresolved_reason": "DBLP person XML unavailable: " + ", ".join(failures),
            "source": f"https://dblp.org{path}.xml",
        }

    try:
        response = requests.get(
            url,
            headers={"User-Agent": "io-links-date-audit/1.0"},
            timeout=30,
        )
    except requests.RequestException as exc:
        return {
            "url": url,
            "unresolved_reason": f"DBLP HTML request failed: {exc}",
            "source": url,
        }
    matches = re.findall(r'"dateModified"\s*:\s*"(\d{4}-\d{2}-\d{2})"', response.text)
    if matches:
        return {
            "url": url,
            "status": "modified",
            "date": max(matches),
            "evidence": "DBLP page JSON-LD dateModified value.",
            "source": url,
        }
    return {
        "url": url,
        "unresolved_reason": f"DBLP HTML HTTP {response.status_code} has no dateModified.",
        "source": url,
    }


def main() -> None:
    targets = []
    for line in INPUT.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if (
            len(fields) == 3
            and fields[1] == "indexed"
            and urlparse(fields[0]).hostname == "dblp.org"
        ):
            targets.append(fields[0])
    results = []
    for count, url in enumerate(targets, 1):
        results.append(audit(url))
        if count % 10 == 0 or count == len(targets):
            print(f"{count}/{len(targets)} checked", flush=True)
    payload = {
        "target_count": len(results),
        "resolved_count": sum(bool(item.get("date")) for item in results),
        "unresolved_count": sum(not item.get("date") for item in results),
        "results": results,
    }
    REPORT.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print({key: value for key, value in payload.items() if key.endswith("_count")})


if __name__ == "__main__":
    main()

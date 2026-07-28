#!/usr/bin/env python3
"""Audit indexed versioned Stackage snapshots and package-version links."""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import requests


INPUT = Path("io_links.md")
RAW = Path("scratch/stackage-dates-continuation-raw.json")
REPORT = Path("scratch/stackage-dates-continuation-audit.json")
SNAPSHOT_RE = re.compile(r"^/(lts-\d+\.\d+)(?:/|$)")
PACKAGE_RE = re.compile(
    r"^/(?:lts/)?package/([A-Za-z][A-Za-z0-9-]*-\d+(?:\.\d+)+(?:\.\d+)*)/?$"
)
PUBLISHED_RE = re.compile(r"Published on (\d{4}-\d{2}-\d{2})")
UPLOADED_RE = re.compile(
    r"Uploaded by .+? at (\d{4}-\d{2}-\d{2})T", re.IGNORECASE
)


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def page_text(value: str) -> str:
    parser = TextExtractor()
    parser.feed(value)
    return " ".join(" ".join(parser.parts).split())


def main() -> None:
    targets = []
    for line in INPUT.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if (
            len(fields) == 3
            and fields[1] == "indexed"
            and urlparse(fields[0]).hostname == "www.stackage.org"
        ):
            targets.append(fields[0])

    session = requests.Session()
    session.headers["User-Agent"] = "io-links-date-audit/1.0"
    raw_records = []
    results = []
    cache: dict[str, tuple[int, str]] = {}
    for url in targets:
        path = urlparse(url).path
        snapshot_match = SNAPSHOT_RE.match(path)
        package_match = PACKAGE_RE.match(path)
        if snapshot_match:
            snapshot = snapshot_match.group(1)
            endpoint = f"https://www.stackage.org/{snapshot}"
            evidence = "Stackage snapshot page explicit Published on date."
        elif package_match:
            package_version = package_match.group(1)
            endpoint = f"https://hackage.haskell.org/package/{package_version}"
            evidence = "Hackage exact package-version page explicit Uploaded by timestamp."
        else:
            results.append(
                {
                    "url": url,
                    "unresolved_reason": "Mutable, unversioned, or unrecognized Stackage page.",
                }
            )
            continue
        if endpoint not in cache:
            response = session.get(endpoint, timeout=40)
            cache[endpoint] = (
                response.status_code,
                page_text(response.text) if response.status_code == 200 else "",
            )
        status_code, text = cache[endpoint]
        raw_records.append(
            {
                "url": url,
                "endpoint": endpoint,
                "status_code": status_code,
                "text": text,
            }
        )
        match = (
            PUBLISHED_RE.search(text)
            if snapshot_match
            else UPLOADED_RE.search(text)
        )
        if match:
            results.append(
                {
                    "url": url,
                    "status": "publication" if snapshot_match else "uploaded",
                    "date": match.group(1),
                    "evidence": evidence,
                    "source": endpoint,
                }
            )
        else:
            results.append(
                {
                    "url": url,
                    "unresolved_reason": (
                        f"Metadata page HTTP {status_code} has no explicit date."
                    ),
                    "source": endpoint,
                }
            )

    RAW.parent.mkdir(parents=True, exist_ok=True)
    RAW.write_text(
        json.dumps({"records": raw_records}, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    report = {
        "target_count": len(targets),
        "resolved_count": sum(bool(item.get("date")) for item in results),
        "unresolved_count": sum(not item.get("date") for item in results),
        "results": results,
    }
    REPORT.write_text(
        json.dumps(report, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print({key: value for key, value in report.items() if key.endswith("_count")})


if __name__ == "__main__":
    main()

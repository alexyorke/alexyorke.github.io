#!/usr/bin/env python3
"""Audit indexed Scala Index artifact-version pages via their release dates."""

from __future__ import annotations

import json
import re
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import requests


INPUT = Path("io_links.md")
RAW = Path("scratch/scala-index-dates-continuation-raw.json")
REPORT = Path("scratch/scala-index-dates-continuation-audit.json")
DATE_RE = re.compile(
    r"Release Date:\s*([A-Z][a-z]{2} \d{1,2}, \d{4})", re.IGNORECASE
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
            and urlparse(fields[0]).hostname == "index.scala-lang.org"
        ):
            targets.append(fields[0])

    session = requests.Session()
    session.headers["User-Agent"] = "io-links-date-audit/1.0"
    raw_records = []
    results = []
    for url in targets:
        response = session.get(url, timeout=30)
        text = page_text(response.text) if response.status_code == 200 else ""
        raw_records.append(
            {
                "url": url,
                "status_code": response.status_code,
                "text": text,
            }
        )
        match = DATE_RE.search(text)
        if match:
            value = datetime.strptime(match.group(1), "%b %d, %Y").date().isoformat()
            results.append(
                {
                    "url": url,
                    "status": "publication",
                    "date": value,
                    "evidence": "Scala Index artifact page explicit Release Date.",
                    "source": url,
                }
            )
        else:
            results.append(
                {
                    "url": url,
                    "unresolved_reason": (
                        f"Scala Index HTTP {response.status_code} has no explicit release date."
                    ),
                    "source": url,
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

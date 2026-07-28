#!/usr/bin/env python3
"""Resolve Sambuz document upload dates from each page's dated metadata line."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


INPUT = Path("io_links.md")
REPORT = Path("scratch/sambuz-date-audit.json")
DATE_RE = re.compile(
    r"\b([A-Z][a-z]{2} \d{1,2}, \d{4})\s+[\d,.]+ likes\s*[•·]\s*[\d,.]+ views"
)


def main() -> None:
    targets = []
    for line in INPUT.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if (
            len(fields) == 3
            and fields[1] == "indexed"
            and urlparse(fields[0]).hostname == "www.sambuz.com"
        ):
            targets.append(fields[0])

    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0 (compatible; io-links-date-audit/1.0)"
    results = []
    for url in targets:
        try:
            response = session.get(url, timeout=30)
            response.raise_for_status()
            text = " ".join(BeautifulSoup(response.text, "html.parser").stripped_strings)
            match = DATE_RE.search(text)
            if not match:
                raise RuntimeError("page metadata upload date not found")
            raw = match.group(1)
            value = datetime.strptime(raw, "%b %d, %Y").date().isoformat()
            results.append(
                {
                    "url": url,
                    "status": "uploaded",
                    "date": value,
                    "evidence": (
                        f"Sambuz document metadata line displays {raw} "
                        "immediately before the page's likes and views counters."
                    ),
                    "source": url,
                }
            )
        except Exception as error:
            results.append(
                {
                    "url": url,
                    "unresolved_reason": f"{type(error).__name__}: {error}",
                    "source": url,
                }
            )

    payload = {
        "target_count": len(results),
        "resolved_count": sum(bool(item.get("date")) for item in results),
        "unresolved_count": sum(not item.get("date") for item in results),
        "results": results,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print({key: value for key, value in payload.items() if key.endswith("_count")})


if __name__ == "__main__":
    main()

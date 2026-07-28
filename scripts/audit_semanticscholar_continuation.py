#!/usr/bin/env python3
"""Cache official Semantic Scholar metadata for current indexed paper URLs."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests


INPUT = Path("io_links.md")
CACHE = Path("scratch/semanticscholar-continuation-raw.json")
ENDPOINT = "https://api.semanticscholar.org/graph/v1/paper/batch"


def main() -> None:
    targets = []
    for line in INPUT.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) != 3 or fields[1] != "indexed":
            continue
        url = fields[0]
        if urlparse(url).hostname != "www.semanticscholar.org":
            continue
        paper_id = unquote(urlparse(url).path.rstrip("/").split("/")[-1])
        targets.append({"url": url, "paper_id": paper_id})

    response = requests.post(
        ENDPOINT,
        params={
            "fields": (
                "paperId,title,year,publicationDate,externalIds,"
                "venue,publicationTypes"
            )
        },
        json={"ids": [target["paper_id"] for target in targets]},
        headers={"User-Agent": "io-links-date-audit/1.0"},
        timeout=60,
    )
    response.raise_for_status()
    records = response.json()
    for target, record in zip(targets, records, strict=True):
        target["metadata"] = record

    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(
        json.dumps(
            {"endpoint": response.url, "targets": targets},
            indent=2,
            ensure_ascii=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        {
            "targets": len(targets),
            "resolved_records": sum(record is not None for record in records),
        }
    )


if __name__ == "__main__":
    main()

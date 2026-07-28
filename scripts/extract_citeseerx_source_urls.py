#!/usr/bin/env python3
"""Print original source URLs for CiteSeerX records still marked indexed."""

from __future__ import annotations

import gzip
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
LINKS = ROOT / "io_links.md"
AUDIT = ROOT / "scratch" / "citeseerx-continuation-audit.json"
URLS = ROOT / "tmp" / "citeseerx-continuation" / "citeseerx_urls.tsv.gz"


def main() -> None:
    indexed_urls = {
        line.split("\t", 1)[0]
        for line in LINKS.read_text(encoding="utf-8").splitlines()
        if "\tindexed\t" in line and "citeseerx.ist.psu.edu" in line
    }
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    records: dict[str, dict[str, object]] = {}
    for item in audit:
        if item["url"] not in indexed_urls:
            continue
        digest = re.search(r"doi=([0-9a-f]+)", item["url"]).group(1)
        for record_id in item.get("matched_record_ids", []):
            records[record_id] = {
                "hash": digest,
                "title": item["candidate_records"][0]["title"],
                "urls": [],
            }

    with gzip.open(URLS, "rt", encoding="utf-8", errors="replace") as source:
        for line in source:
            record_id, separator, url = line.rstrip("\n").partition("\t")
            if separator and record_id in records:
                records[record_id]["urls"].append(url)

    print(json.dumps(records, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()

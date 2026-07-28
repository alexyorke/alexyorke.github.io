#!/usr/bin/env python3
"""Transfer dates between ResearchGate URLs sharing a publication identifier."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse


INPUT = Path("io_links.md")
REPORT = Path("scratch/researchgate-publication-id-duplicates.json")
ID_RE = re.compile(r"/publication/(\d+)")


def main() -> None:
    rows = []
    for line in INPUT.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) != 3:
            continue
        parsed = urlparse(fields[0])
        if not parsed.netloc.lower().endswith("researchgate.net"):
            continue
        match = ID_RE.search(parsed.path)
        if match:
            rows.append((fields, match.group(1)))

    resolved_by_id = defaultdict(set)
    source_by_id = {}
    for (url, status, date), publication_id in rows:
        if status != "indexed":
            resolved_by_id[publication_id].add((status, date))
            source_by_id[publication_id] = url

    results = []
    for (url, status, _), publication_id in rows:
        values = resolved_by_id[publication_id]
        if status != "indexed" or len(values) != 1:
            continue
        new_status, date = next(iter(values))
        results.append(
            {
                "url": url,
                "status": new_status,
                "date": date,
                "source": source_by_id[publication_id],
                "evidence": (
                    "ResearchGate URL shares publication identifier "
                    f"{publication_id} with an already dated row."
                ),
            }
        )

    payload = {
        "target_count": len(results),
        "resolved_count": len(results),
        "unresolved_count": 0,
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

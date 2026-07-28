#!/usr/bin/env python3
"""Resolve cached documents that are byte-identical to an already dated URL."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse


INPUT = Path("io_links.md")
CACHE = Path("tmp/pdfs/indexed")
REPORT = Path("scratch/cached-document-duplicate-audit.json")
DOCUMENT_RE = re.compile(r"\.(?:pdf|ps|ps\.gz)(?:$|[?#])", re.I)


def cache_path(url: str) -> Path:
    suffix = ".ps" if re.search(r"\.ps(?:$|[?#])", urlparse(url).path, re.I) else ".pdf"
    return CACHE / f"{hashlib.sha256(url.encode()).hexdigest()[:20]}{suffix}"


def main() -> None:
    records = []
    by_digest: dict[str, list[dict]] = defaultdict(list)
    for line in INPUT.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) != 3 or not DOCUMENT_RE.search(urlparse(fields[0]).path):
            continue
        path = cache_path(fields[0])
        if not path.exists() or path.stat().st_size <= 1_000:
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        record = {
            "url": fields[0],
            "status": fields[1],
            "date": fields[2],
            "path": str(path),
        }
        records.append(record)
        by_digest[digest].append(record)

    results = []
    for digest, group in by_digest.items():
        known = {
            (item["status"], item["date"])
            for item in group
            if item["status"] != "indexed"
        }
        if len(known) != 1:
            continue
        status, value = known.pop()
        for item in group:
            if item["status"] != "indexed":
                continue
            results.append(
                {
                    "url": item["url"],
                    "status": status,
                    "date": value,
                    "source": next(
                        peer["url"] for peer in group if peer["status"] != "indexed"
                    ),
                    "evidence": (
                        f"Byte-identical cached document SHA-256 {digest}; "
                        "the duplicate URL already has this source-backed date."
                    ),
                }
            )

    payload = {
        "target_count": len(results),
        "resolved_count": len(results),
        "unresolved_count": 0,
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

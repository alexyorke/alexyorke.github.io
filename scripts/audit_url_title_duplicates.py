#!/usr/bin/env python3
"""Resolve mirrors whose URL-encoded title exactly matches an already dated work."""

from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import unquote, urlparse


INPUT = Path("io_links.md")
REPORT = Path("scratch/url-title-duplicate-audit.json")
GENERIC = {
    "index",
    "home",
    "download",
    "document",
    "publication",
    "paper",
    "monads",
    "haskell",
    "io",
    "input output",
}


def title_key(url: str) -> str | None:
    parsed = urlparse(url)
    path = unquote(parsed.path).strip("/")
    if not path:
        return None
    match = re.search(r"/publication/\d+_([^/]+)", "/" + path, re.I)
    if match:
        raw = match.group(1)
    elif parsed.hostname and "academia.edu" in parsed.hostname:
        parts = path.split("/", 1)
        raw = parts[1] if len(parts) == 2 else ""
    else:
        raw = path.rsplit("/", 1)[-1]
    raw = re.sub(r"\.(?:pdf|ps|html?|php|aspx?)$", "", raw, flags=re.I)
    raw = re.sub(
        r"-(?:ppt-)?presentation-\d+$|-(?:pdf-)?document-\d+$|-\d{5,}$",
        "",
        raw,
        flags=re.I,
    )
    raw = re.sub(r"-[a-z0-9]{8,12}$", "", raw, flags=re.I)
    normalized = unicodedata.normalize("NFKD", raw).casefold()
    tokens = re.findall(r"[a-z0-9]+", normalized)
    key = " ".join(tokens)
    if len(tokens) < 4 or len(key) < 24 or key in GENERIC:
        return None
    return key


def main() -> None:
    records = []
    known: dict[str, list[dict]] = defaultdict(list)
    for line in INPUT.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) != 3:
            continue
        key = title_key(fields[0])
        if not key:
            continue
        item = {
            "url": fields[0],
            "status": fields[1],
            "date": fields[2],
            "key": key,
        }
        records.append(item)
        if fields[1] != "indexed":
            known[key].append(item)

    results = []
    resolved_urls = set()
    for item in records:
        if item["status"] != "indexed":
            continue
        peers = known.get(item["key"], [])
        values = {(peer["status"], peer["date"]) for peer in peers}
        if len(values) != 1:
            continue
        status, value = values.pop()
        results.append(
            {
                "url": item["url"],
                "status": status,
                "date": value,
                "source": peers[0]["url"],
                "evidence": (
                    "Exact normalized title match to an already source-dated mirror: "
                    f"{item['key']}"
                ),
            }
        )
        resolved_urls.add(item["url"])

    dated_records = [item for items in known.values() for item in items]
    for item in records:
        if item["status"] != "indexed" or item["url"] in resolved_urls:
            continue
        ranked = sorted(
            (
                (
                    SequenceMatcher(None, item["key"], peer["key"]).ratio(),
                    peer,
                )
                for peer in dated_records
            ),
            key=lambda row: row[0],
            reverse=True,
        )[:2]
        if len(ranked) < 2:
            continue
        score, peer = ranked[0]
        margin = score - ranked[1][0]
        if score < 0.94 or margin < 0.2:
            continue
        results.append(
            {
                "url": item["url"],
                "status": peer["status"],
                "date": peer["date"],
                "source": peer["url"],
                "evidence": (
                    "Unique near-exact normalized URL-title match "
                    f"(similarity {score:.3f}, margin {margin:.3f}): "
                    f"{item['key']} -> {peer['key']}"
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

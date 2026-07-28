#!/usr/bin/env python3
"""Promote conservative dates from previously cached scholarly metadata."""

from __future__ import annotations

import html
import json
import re
import unicodedata
from datetime import date
from pathlib import Path


INPUT = Path("io_links.md")
REPORT = Path("scratch/cached-scholarly-years-audit.json")


def tokens(value: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", html.unescape(str(value))).casefold()
    return set(re.findall(r"[a-z0-9]+", normalized))


def rg_title(url: str) -> str:
    match = re.search(r"/publication/\d+_([^?#]+)", url)
    return re.sub(r"[_-]+", " ", match.group(1)) if match else ""


def crossref_date(item: dict) -> str | None:
    for field in ("published-online", "published-print", "published", "issued"):
        parts = (item.get(field) or {}).get("date-parts") or []
        if not parts or not parts[0]:
            continue
        values = parts[0]
        try:
            if len(values) >= 3:
                return date(values[0], values[1], values[2]).isoformat()
            if len(values) == 2:
                return f"{values[0]:04d}-{values[1]:02d}"
            return f"{values[0]:04d}"
        except (TypeError, ValueError):
            continue
    return None


def main() -> None:
    indexed = {
        line.split("\t")[0]
        for line in INPUT.read_text(encoding="utf-8").splitlines()
        if "\tindexed\t" in line
    }
    results = []

    citeseer = json.loads(
        Path("scratch/citeseerx-continuation-audit.json").read_text(encoding="utf-8")
    )
    for item in citeseer:
        if item.get("url") not in indexed or item.get("date"):
            continue
        years = {
            str(record.get("year"))
            for record in item.get("candidate_records", [])
            if re.fullmatch(r"(?:19|20)\d{2}", str(record.get("year") or ""))
        }
        if len(years) == 1:
            results.append(
                {
                    "url": item["url"],
                    "status": "publication",
                    "date": years.pop(),
                    "evidence": "The CiteSeerX paper record has one unambiguous valid year across every record matched to this document checksum.",
                    "source": item.get("source"),
                }
            )

    cache = json.loads(
        Path("scratch/researchgate-dblp-continuation-cache.json").read_text(
            encoding="utf-8"
        )
    )
    for key, payload in cache.items():
        if not key.startswith("crossref:"):
            continue
        url = key.split(":", 1)[1]
        if url not in indexed:
            continue
        query_tokens = tokens(rg_title(url))
        ranked = []
        for candidate in payload.get("items", []):
            candidate_title = (candidate.get("title") or [""])[0]
            candidate_tokens = tokens(candidate_title)
            intersection = len(query_tokens & candidate_tokens)
            union = len(query_tokens | candidate_tokens)
            smaller = min(len(query_tokens), len(candidate_tokens))
            jaccard = intersection / union if union else 0
            coverage = intersection / smaller if smaller else 0
            ranked.append((jaccard, coverage, len(candidate_tokens), candidate))
        ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)
        if not ranked:
            continue
        jaccard, coverage, length, candidate = ranked[0]
        value = crossref_date(candidate)
        if jaccard < 0.65 or coverage < 0.95 or length < 3 or not value:
            continue
        results.append(
            {
                "url": url,
                "status": "publication",
                "date": value,
                "evidence": "High-overlap Crossref title match cached during the ResearchGate audit.",
                "source": f"https://api.crossref.org/works/{candidate.get('DOI')}",
                "matched_title": (candidate.get("title") or [None])[0],
                "doi": candidate.get("DOI"),
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

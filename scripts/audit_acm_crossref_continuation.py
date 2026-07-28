#!/usr/bin/env python3
"""Audit indexed ACM DOI links using exact Crossref or OpenAlex metadata."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

import requests


INPUT = Path("io_links.md")
RAW = Path("scratch/acm-crossref-continuation-raw.json")
REPORT = Path("scratch/acm-crossref-continuation-audit.json")
DOI_RE = re.compile(r"^/doi/(?:abs/|pdf/|book/)?(10\.\d{4,9}/[^/?#]+)")


def date_value(message: dict) -> str | None:
    for key in ("published", "published-print", "published-online", "issued"):
        parts = message.get(key, {}).get("date-parts", [])
        if not parts or not parts[0]:
            continue
        values = parts[0]
        if len(values) >= 3:
            return f"{values[0]:04d}-{values[1]:02d}-{values[2]:02d}"
        if len(values) == 2:
            return f"{values[0]:04d}-{values[1]:02d}"
        return f"{values[0]:04d}"
    return None


def openalex_lookup(session: requests.Session, doi: str) -> tuple[dict | None, dict]:
    endpoint = "https://api.openalex.org/works"
    response = session.get(endpoint, params={"filter": f"doi:{doi}"}, timeout=30)
    raw = {
        "endpoint": response.url,
        "status_code": response.status_code,
        "body": response.text if response.status_code == 200 else None,
    }
    if response.status_code != 200:
        return None, raw
    candidates = response.json().get("results") or []
    expected = f"https://doi.org/{doi}".casefold()
    for candidate in candidates:
        if str(candidate.get("doi") or "").casefold() == expected:
            return candidate, raw
    return None, raw


def main() -> None:
    targets = []
    for line in INPUT.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) != 3 or fields[1] != "indexed":
            continue
        parsed = urlparse(fields[0])
        if parsed.hostname != "dl.acm.org":
            continue
        match = DOI_RE.match(parsed.path)
        if match:
            targets.append((fields[0], unquote(match.group(1))))

    session = requests.Session()
    session.headers["User-Agent"] = "io-links-date-audit/1.0"
    raw_records = []
    results = []
    for index, (url, doi) in enumerate(targets, 1):
        # Crossref's work endpoint requires the DOI path separator to remain a
        # literal slash; percent-encoding it makes otherwise valid DOIs 404.
        endpoint = f"https://api.crossref.org/works/{quote(doi, safe='/')}"
        response = None
        for attempt in range(4):
            response = session.get(endpoint, timeout=30)
            if response.status_code != 429:
                break
            time.sleep(1 + attempt * 2)
        assert response is not None
        raw_record = {
            "url": url,
            "doi": doi,
            "crossref_status_code": response.status_code,
            "crossref_body": response.text if response.status_code == 200 else None,
        }
        raw_records.append(raw_record)
        if response.status_code != 200:
            candidate, openalex_raw = openalex_lookup(session, doi)
            raw_record["openalex"] = openalex_raw
            if candidate and candidate.get("publication_date"):
                results.append(
                    {
                        "url": url,
                        "status": "publication",
                        "date": candidate["publication_date"],
                        "evidence": (
                            "OpenAlex exact DOI record publication date; "
                            "Crossref did not return the DOI."
                        ),
                        "source": openalex_raw["endpoint"],
                        "doi": candidate.get("doi"),
                        "title": candidate.get("title"),
                    }
                )
            else:
                results.append(
                    {
                        "url": url,
                        "unresolved_reason": (
                            f"Crossref HTTP {response.status_code}; no exact "
                            f"dated OpenAlex DOI record (HTTP "
                            f"{openalex_raw['status_code']})"
                        ),
                        "source": openalex_raw["endpoint"],
                    }
                )
        else:
            message = response.json().get("message", {})
            value = date_value(message)
            if value:
                results.append(
                    {
                        "url": url,
                        "status": "publication",
                        "date": value,
                        "evidence": "Crossref DOI record publication date.",
                        "source": endpoint,
                        "doi": message.get("DOI", doi),
                        "title": (message.get("title") or [None])[0],
                    }
                )
            else:
                results.append(
                    {
                        "url": url,
                        "unresolved_reason": "Crossref DOI record has no publication date",
                        "source": endpoint,
                    }
                )
        print(f"{index}/{len(targets)} {doi} HTTP {response.status_code}", flush=True)
        time.sleep(0.1)

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

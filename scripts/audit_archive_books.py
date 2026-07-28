#!/usr/bin/env python3
"""Resolve Archive.org and Open Library item dates from their public APIs."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from dateutil import parser as date_parser


def normalize(value: object) -> str | None:
    if isinstance(value, dict):
        value = value.get("value")
    if not value:
        return None
    text = str(value).strip()
    year = re.fullmatch(r"(18|19|20)\d{2}", text)
    if year:
        return text
    try:
        parsed = date_parser.parse(text, fuzzy=False, default=datetime(1, 1, 1))
    except (OverflowError, ValueError):
        return None
    has_month = bool(
        re.search(
            r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)",
            text,
            re.I,
        )
        or re.search(r"\d{4}[-/]\d{1,2}", text)
    )
    has_day = bool(
        re.search(r"\b\d{1,2}[, ]+\d{4}\b", text)
        or re.search(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", text)
    )
    if has_day:
        return parsed.date().isoformat()
    if has_month:
        return f"{parsed.year:04d}-{parsed.month:02d}"
    return f"{parsed.year:04d}"


def archive_item(session: requests.Session, url: str) -> dict:
    identifier = urlparse(url).path.strip("/").split("/")[1]
    response = session.get(f"https://archive.org/metadata/{identifier}", timeout=30)
    item = {"url": url, "status": None, "date": None, "source": "archive-org-api"}
    if not response.ok:
        item["error"] = f"HTTP {response.status_code}"
        return item
    metadata = response.json().get("metadata") or {}
    publication = normalize(metadata.get("date") or metadata.get("year"))
    uploaded = normalize(metadata.get("publicdate") or metadata.get("addeddate"))
    if publication:
        item.update(
            status="publication",
            date=publication,
            evidence="Archive.org metadata date/year",
        )
    elif uploaded:
        item.update(
            status="uploaded",
            date=uploaded,
            evidence="Archive.org publicdate/addeddate",
        )
    return item


def openlibrary_item(session: requests.Session, url: str) -> dict:
    parts = urlparse(url).path.strip("/").split("/")
    item = {"url": url, "status": None, "date": None, "source": "openlibrary-api"}
    if len(parts) < 2 or parts[0] not in {"books", "works", "authors"}:
        return item
    kind, key = parts[0], parts[1]
    response = session.get(f"https://openlibrary.org/{kind}/{key}.json", timeout=30)
    if not response.ok:
        item["error"] = f"HTTP {response.status_code}"
        return item
    node = response.json()
    publication = normalize(node.get("publish_date") or node.get("first_publish_date"))
    evidence = f"{kind} publish date"
    if not publication and kind == "works":
        editions = session.get(
            f"https://openlibrary.org/works/{key}/editions.json?limit=100", timeout=30
        )
        if editions.ok:
            dates = [
                normalize(entry.get("publish_date"))
                for entry in editions.json().get("entries", [])
            ]
            dates = [value for value in dates if value]
            if dates:
                publication = min(dates)
                evidence = "earliest edition publish date"
    if publication:
        item.update(
            status="publication",
            date=publication,
            evidence=evidence,
        )
    elif kind != "authors":
        created = normalize(node.get("created"))
        if created:
            item.update(
                status="created",
                date=created,
                evidence=f"{kind} record creation date",
            )
    return item


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, default=Path("io_links.md"))
    parser.add_argument(
        "--report", type=Path, default=Path("scratch/archive-books-audit.json")
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    lines = args.file.read_text(encoding="utf-8").splitlines()
    urls = []
    for line in lines:
        parts = line.split("\t")
        if len(parts) == 3 and parts[1] == "indexed":
            host = urlparse(parts[0]).netloc.lower()
            if host in {"archive.org", "openlibrary.org"}:
                urls.append(parts[0])
    session = requests.Session()
    results = [
        archive_item(session, url)
        if urlparse(url).netloc.lower() == "archive.org"
        else openlibrary_item(session, url)
        for url in urls
    ]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(results, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    if args.apply:
        resolved = {item["url"]: item for item in results if item.get("date")}
        changed = 0
        for index, line in enumerate(lines):
            parts = line.split("\t")
            item = resolved.get(parts[0]) if len(parts) == 3 else None
            if len(parts) == 3 and parts[1] == "indexed" and item:
                lines[index] = f"{parts[0]}\t{item['status']}\t{item['date']}"
                changed += 1
        args.file.write_text(
            "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
        )
        print(f"Updated {changed}/{len(urls)} rows", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

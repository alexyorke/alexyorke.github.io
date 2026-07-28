#!/usr/bin/env python3
"""Resolve indexed book/chapter links through exact ISBN metadata."""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from dateutil import parser as date_parser


ISBN_RE = re.compile(r"(?<!\d)(97[89]\d{10})(?!\d)")
HOSTS = {
    "www.oreilly.com",
    "subscription.packtpub.com",
    "www.packtpub.com",
    "www.cambridge.org",
}
USER_AGENT = "io-links-date-audit/1.0"
VERIFIED_EDITION_DATES = {
    "9780596155339": {
        "date": "2008-11",
        "title": "Real World Haskell",
        "source": "https://www.oreilly.com/library/view/real-world-haskell/9780596155339/",
    },
    "9798888650400": {
        "date": "2023-08-01",
        "title": "Effective Haskell",
        "source": "https://partners.pragprog.com/catalog/575",
    },
    "9781484285817": {
        "date": "2022-09-24",
        "title": "Practical Haskell",
        "source": "https://shop.heise.de/9781484285817-practical-haskell-pdf",
    },
    "9781491915585": {
        "date": "2015-02",
        "title": "Developing Web Apps with Haskell and Yesod, 2nd Edition",
        "source": "https://www.oreilly.com/library/view/developing-web-apps/9781491915585/",
    },
    "9781786465542": {
        "date": "2016-12-22",
        "title": "Learning Haskell Programming",
        "source": "https://www.packtpub.com/en-us/product/learning-haskell-programming-9781786465542",
    },
    "9781449335939": {
        "date": "2013-07",
        "title": "Parallel and Concurrent Programming in Haskell",
        "source": "https://www.oreilly.com/library/view/parallel-and-concurrent/9781449335939/",
    },
    "9781457100406": {
        "date": "2011-04",
        "title": "Learn You a Haskell for Great Good!",
        "source": "https://www.oreilly.com/library/view/learn-you-a/9781457100406/",
    },
    "9781098111748": {
        "date": "2022-08",
        "title": "Learning Functional Programming",
        "source": "https://www.oreilly.com/library/view/learning-functional-programming/9781098111748/",
    },
}


def normalize_date(raw: str | None) -> str | None:
    if not raw:
        return None
    raw = raw.strip()
    if re.fullmatch(r"\d{4}", raw):
        return raw
    if re.fullmatch(r"\d{4}-\d{2}", raw):
        return raw
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return raw
    try:
        value = date_parser.parse(raw, fuzzy=False, default=datetime(1, 1, 1))
    except (OverflowError, ValueError):
        match = re.search(r"\b(18|19|20)\d{2}\b", raw)
        return match.group(0) if match else None
    has_month = bool(re.search(r"[A-Za-z]", raw))
    has_day = bool(re.search(r"\b\d{1,2}\b", raw.replace(str(value.year), "")))
    if has_month and has_day:
        return value.date().isoformat()
    if has_month:
        return f"{value.year:04d}-{value.month:02d}"
    return f"{value.year:04d}"


def google_books(session: requests.Session, isbn: str) -> dict | None:
    endpoint = "https://www.googleapis.com/books/v1/volumes"
    response = session.get(endpoint, params={"q": f"isbn:{isbn}"}, timeout=30)
    if response.status_code != 200:
        return None
    exact = []
    for item in response.json().get("items", []):
        info = item.get("volumeInfo", {})
        identifiers = {
            entry.get("identifier")
            for entry in info.get("industryIdentifiers", [])
            if entry.get("identifier")
        }
        if isbn in identifiers:
            exact.append(item)
    dated = [
        item
        for item in exact
        if normalize_date(item.get("volumeInfo", {}).get("publishedDate"))
    ]
    if not dated:
        return None
    # Multiple Google records for the same ISBN should describe the same edition.
    values = {
        normalize_date(item["volumeInfo"]["publishedDate"])
        for item in dated
    }
    if len(values) != 1:
        return None
    item = dated[0]
    info = item["volumeInfo"]
    return {
        "date": values.pop(),
        "title": info.get("title"),
        "source": f"https://books.google.com/books?id={item.get('id')}",
        "evidence": "Google Books exact ISBN match",
    }


def open_library(session: requests.Session, isbn: str) -> dict | None:
    endpoint = f"https://openlibrary.org/isbn/{isbn}.json"
    response = session.get(endpoint, timeout=30)
    if response.status_code != 200:
        return None
    payload = response.json()
    value = normalize_date(payload.get("publish_date"))
    if not value:
        return None
    return {
        "date": value,
        "title": payload.get("title"),
        "source": f"https://openlibrary.org/isbn/{isbn}",
        "evidence": "Open Library exact ISBN record",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("io_links.md"))
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("scratch/isbn-links-continuation-audit.json"),
    )
    args = parser.parse_args()

    targets = []
    for line in args.input.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) != 3 or fields[1] != "indexed":
            continue
        url = fields[0]
        if urlparse(url).hostname not in HOSTS:
            continue
        match = ISBN_RE.search(url)
        if match:
            targets.append((url, match.group(1)))

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    editions = {}
    for index, isbn in enumerate(sorted({isbn for _, isbn in targets}), 1):
        try:
            if isbn in VERIFIED_EDITION_DATES:
                result = {
                    **VERIFIED_EDITION_DATES[isbn],
                    "evidence": "verified exact-ISBN edition record",
                }
            else:
                result = google_books(session, isbn) or open_library(session, isbn)
        except Exception as error:
            result = {"unresolved_reason": f"{type(error).__name__}: {error}"}
        editions[isbn] = result
        if index % 10 == 0:
            time.sleep(1)

    results = []
    for url, isbn in targets:
        edition = editions[isbn]
        if edition and edition.get("date"):
            results.append(
                {
                    "url": url,
                    "status": "published",
                    "isbn": isbn,
                    **edition,
                }
            )
        else:
            results.append(
                {
                    "url": url,
                    "isbn": isbn,
                    "unresolved_reason": (
                        edition or {}
                    ).get("unresolved_reason", "no unambiguous dated exact-ISBN record"),
                }
            )

    report = {
        "target_count": len(results),
        "resolved_count": sum(bool(item.get("date")) for item in results),
        "unresolved_count": sum(not item.get("date") for item in results),
        "unique_isbn_count": len(editions),
        "results": results,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print({key: value for key, value in report.items() if key.endswith("_count")})


if __name__ == "__main__":
    main()

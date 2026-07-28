#!/usr/bin/env python3
"""Audit current indexed Manning book URLs using official product metadata."""

from __future__ import annotations

import hashlib
import html as html_module
import json
import re
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

import requests


INPUT = Path("io_links.md")
OUTPUT = Path("scratch/manning-continuation-audit.json")
CACHE = Path("tmp/manning-continuation")
MONTH_YEAR_RE = re.compile(
    r"\b("
    r"January|February|March|April|May|June|July|August|"
    r"September|October|November|December"
    r")\s+(\d{4})\b"
)


def targets() -> list[str]:
    urls: list[str] = []
    for line in INPUT.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if (
            len(fields) == 3
            and fields[1] == "indexed"
            and urlparse(fields[0]).hostname == "www.manning.com"
            and urlparse(fields[0]).path.startswith("/books/")
        ):
            urls.append(fields[0])
    assert len(urls) == len(set(urls))
    return urls


def fetch(session: requests.Session, url: str) -> tuple[str, str]:
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE / f"{hashlib.sha256(url.encode()).hexdigest()}.html"
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8"), str(cache_path)
    response = session.get(url, timeout=30)
    response.raise_for_status()
    cache_path.write_text(response.text, encoding="utf-8", newline="\n")
    return response.text, str(cache_path)


def extract(html: str) -> tuple[str, str] | None:
    block = re.search(
        r'<div class="product-meta">(.*?)</div>', html, re.DOTALL | re.IGNORECASE
    )
    if not block:
        return None
    plain = html_module.unescape(re.sub(r"<[^>]+>", " ", block.group(1)))
    plain = re.sub(r"\s+", " ", plain).strip()
    match = MONTH_YEAR_RE.search(plain)
    isbn = re.search(r"\bISBN\s+(\d{10,13})\b", plain)
    if not match or not isbn:
        return None
    value = datetime.strptime(
        f"{match.group(1)} {match.group(2)}", "%B %Y"
    ).strftime("%Y-%m")
    return value, isbn.group(1)


def main() -> None:
    current = targets()
    session = requests.Session()
    session.headers["User-Agent"] = "io-links-date-audit/1.0"
    results: list[dict[str, str]] = []
    unresolved: list[dict[str, str]] = []

    for url in current:
        try:
            body, cache_path = fetch(session, url)
            parsed = extract(body)
        except requests.RequestException as exc:
            unresolved.append(
                {"url": url, "reason": f"request failed: {type(exc).__name__}: {exc}"}
            )
            continue
        if parsed is None:
            unresolved.append(
                {
                    "url": url,
                    "reason": "Official product metadata lacked month/year plus ISBN.",
                    "cache_path": cache_path,
                }
            )
            continue
        value, isbn = parsed
        normalized = value + "-01"
        assert date.fromisoformat(normalized) <= date.today()
        results.append(
            {
                "url": url,
                "status": "publication",
                "date": value,
                "confidence": "high",
                "evidence": (
                    f"Official Manning product metadata gives publication month "
                    f"{value} and ISBN {isbn}."
                ),
                "source_url": url,
                "cache_path": cache_path,
            }
        )

    assert {item["url"] for item in results + unresolved} == set(current)
    assert len(results) + len(unresolved) == len(current)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(
            {
                "summary": {
                    "targets": len(current),
                    "resolved": len(results),
                    "unresolved": len(unresolved),
                },
                "results": results,
                "unresolved": unresolved,
            },
            indent=2,
            ensure_ascii=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        {
            "targets": len(current),
            "resolved": len(results),
            "unresolved": len(unresolved),
            "output": str(OUTPUT),
        }
    )


if __name__ == "__main__":
    main()

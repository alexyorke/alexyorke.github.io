#!/usr/bin/env python3
"""Audit current indexed Haskell Weekly and Zenn URLs for first-party dates."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import requests


INPUT = Path("io_links.md")
OUTPUT = Path("scratch/haskellweekly-zenn-continuation-audit.json")
CACHE = Path("tmp/haskellweekly-zenn-continuation")
HOSTS = {"haskellweekly.news", "zenn.dev"}
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def current_targets() -> list[str]:
    targets: list[str] = []
    for line in INPUT.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) != 3 or fields[1] != "indexed":
            continue
        if urlparse(fields[0]).hostname in HOSTS:
            targets.append(fields[0])
    assert len(targets) == len(set(targets)), "duplicate target URLs"
    return targets


def fetch(session: requests.Session, url: str) -> tuple[str, str]:
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE / f"{hashlib.sha256(url.encode()).hexdigest()}.html"
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8"), str(cache_path)
    response = session.get(url, timeout=30)
    response.raise_for_status()
    cache_path.write_text(response.text, encoding="utf-8", newline="\n")
    return response.text, str(cache_path)


def extract(url: str, html: str) -> tuple[str, str, str] | None:
    path = urlparse(url).path
    if urlparse(url).hostname == "haskellweekly.news":
        if path.startswith("/issue/"):
            match = re.search(
                r"<h3[^>]*>\s*Issue\s+\d+\s*<span[^>]*>"
                r"(\d{4}-\d{2}-\d{2})</span>",
                html,
                re.IGNORECASE,
            )
            if match:
                return (
                    "published",
                    match.group(1),
                    "Official issue page labels the issue with this date.",
                )
        if path.startswith("/episode/"):
            match = re.search(
                r"was published on\s+(\d{4}-\d{2}-\d{2})", html, re.IGNORECASE
            )
            if match:
                return (
                    "published",
                    match.group(1),
                    "Official episode page explicitly states its publication date.",
                )
        return None

    if "/articles/" in path:
        match = re.search(r'"publishedAt":"(\d{4}-\d{2}-\d{2})T', html)
        if match:
            return (
                "published",
                match.group(1),
                "Zenn page data exposes the article's publishedAt timestamp.",
            )
    if "/scraps/" in path:
        match = re.search(
            r'"commentsCount":\d+,"createdAt":"(\d{4}-\d{2}-\d{2})T', html
        )
        if match:
            return (
                "created",
                match.group(1),
                "Zenn page data exposes the scrap's createdAt timestamp.",
            )
    return None


def main() -> None:
    targets = current_targets()
    results: list[dict[str, str]] = []
    unresolved: list[dict[str, str]] = []
    session = requests.Session()
    session.headers["User-Agent"] = "io-links-date-audit/1.0"

    for url in targets:
        try:
            html, cache_path = fetch(session, url)
            found = extract(url, html)
        except requests.RequestException as exc:
            unresolved.append(
                {"url": url, "reason": f"request failed: {type(exc).__name__}: {exc}"}
            )
            continue
        if found is None:
            unresolved.append(
                {
                    "url": url,
                    "reason": "No item-specific first-party publication/creation date found.",
                    "cache_path": cache_path,
                }
            )
            continue
        status, value, evidence = found
        assert DATE_RE.fullmatch(value)
        assert date.fromisoformat(value) <= date.today()
        results.append(
            {
                "url": url,
                "status": status,
                "date": value,
                "confidence": "high",
                "evidence": evidence,
                "source_url": url,
                "cache_path": cache_path,
            }
        )

    covered = {item["url"] for item in results + unresolved}
    assert covered == set(targets), "report coverage differs from current targets"
    assert len(results) + len(unresolved) == len(targets)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(
            {
                "summary": {
                    "targets": len(targets),
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
            "targets": len(targets),
            "resolved": len(results),
            "unresolved": len(unresolved),
            "output": str(OUTPUT),
        }
    )


if __name__ == "__main__":
    main()

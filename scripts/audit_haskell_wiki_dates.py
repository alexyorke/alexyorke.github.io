#!/usr/bin/env python3
"""Resolve HaskellWiki page creation dates through MediaWiki revision history."""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import requests


INPUT = Path("io_links.md")
REPORT = Path("scratch/haskell-wiki-dates-audit.json")
API = "https://wiki.haskell.org/api.php"


def wiki_title(url: str) -> str | None:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if host not in {"haskell.org", "www.haskell.org", "wiki.haskell.org"}:
        return None
    query_title = parse_qs(parsed.query).get("title")
    if query_title:
        return query_title[0].replace("_", " ")
    marker = "/haskellwiki/"
    if marker in parsed.path:
        return unquote(parsed.path.split(marker, 1)[1]).replace("_", " ")
    if host == "wiki.haskell.org" and parsed.path not in {"", "/"}:
        return unquote(parsed.path.lstrip("/")).replace("_", " ")
    return None


def normalized(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def resolve_title(session: requests.Session, title: str) -> str:
    response = session.get(
        API,
        params={
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": f'intitle:"{title}"',
            "srlimit": "10",
        },
        timeout=30,
    )
    candidates = response.json().get("query", {}).get("search", []) if response.ok else []
    query = normalized(title)
    ranked = sorted(
        (
            (
                SequenceMatcher(None, query, normalized(item.get("title", ""))).ratio(),
                item.get("title", ""),
            )
            for item in candidates
        ),
        reverse=True,
    )
    if ranked and ranked[0][0] >= 0.9:
        return ranked[0][1]
    return title


def main() -> None:
    targets = []
    for line in INPUT.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) == 3 and fields[1] == "indexed":
            title = wiki_title(fields[0])
            if title:
                targets.append((fields[0], title))

    session = requests.Session()
    session.headers["User-Agent"] = "io-links-date-audit/1.0"
    results = []
    for url, title in targets:
        response = session.get(
            API,
            params={
                "action": "query",
                "format": "json",
                "prop": "revisions",
                "rvprop": "timestamp",
                "rvdir": "newer",
                "rvlimit": "1",
                "titles": title,
                "redirects": "1",
            },
            timeout=30,
        )
        payload = response.json() if response.status_code == 200 else {}
        pages = payload.get("query", {}).get("pages", {})
        page = next(iter(pages.values()), {})
        revisions = page.get("revisions") or []
        timestamp = revisions[0].get("timestamp") if revisions else None
        if not timestamp:
            resolved_title = resolve_title(session, title)
            if resolved_title != title:
                response = session.get(
                    API,
                    params={
                        "action": "query",
                        "format": "json",
                        "prop": "revisions",
                        "rvprop": "timestamp",
                        "rvdir": "newer",
                        "rvlimit": "1",
                        "titles": resolved_title,
                        "redirects": "1",
                    },
                    timeout=30,
                )
                payload = response.json() if response.status_code == 200 else {}
                pages = payload.get("query", {}).get("pages", {})
                page = next(iter(pages.values()), {})
                revisions = page.get("revisions") or []
                timestamp = revisions[0].get("timestamp") if revisions else None
        if timestamp:
            results.append(
                {
                    "url": url,
                    "status": "created",
                    "date": timestamp[:10],
                    "evidence": "Timestamp of the first MediaWiki revision.",
                    "source": response.url,
                    "title": page.get("title", title),
                }
            )
        else:
            results.append(
                {
                    "url": url,
                    "unresolved_reason": f"HaskellWiki API has no revision history for {title!r}.",
                    "source": response.url,
                }
            )

    report = {
        "target_count": len(results),
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

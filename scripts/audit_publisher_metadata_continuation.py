#!/usr/bin/env python3
"""Audit indexed ScienceDirect and Microsoft Research links via public metadata."""

from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests


USER_AGENT = "io-links-date-audit/1.0"
PII_RE = re.compile(r"/pii/([A-Za-z0-9]+)")
MICROSOFT_PATH_RE = re.compile(r"/research/publication/([^/?#]+)/?")


def normalized(value: str) -> str:
    value = unicodedata.normalize("NFKD", unquote(value)).lower()
    return " ".join(re.findall(r"[a-z0-9]+", value))


def normalize_date(value: str | None) -> str | None:
    if not value:
        return None
    match = re.fullmatch(r"(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?", value.strip())
    if not match:
        return None
    year, month, day = match.groups()
    if day:
        return f"{year}-{month}-{day}"
    if month:
        return f"{year}-{month}"
    return year


def audit_sciencedirect(session: requests.Session, url: str) -> dict:
    match = PII_RE.search(url)
    if not match:
        return {"url": url, "unresolved_reason": "PII missing from URL"}
    pii = match.group(1)
    endpoint = f"https://api.elsevier.com/content/article/pii/{pii}"
    response = None
    for attempt in range(4):
        response = session.get(
            endpoint,
            headers={"Accept": "application/json"},
            params={"httpAccept": "application/json"},
            timeout=30,
        )
        if response.status_code != 429:
            break
        time.sleep(2 + attempt * 2)
    assert response is not None
    if response.status_code != 200:
        return {
            "url": url,
            "unresolved_reason": f"Elsevier API HTTP {response.status_code}",
            "source": endpoint,
        }
    core = response.json().get("full-text-retrieval-response", {}).get("coredata", {})
    value = normalize_date(core.get("prism:coverDate"))
    if not value:
        return {
            "url": url,
            "unresolved_reason": "Elsevier metadata has no cover date",
            "source": endpoint,
        }
    return {
        "url": url,
        "status": "published",
        "date": value,
        "evidence": "Elsevier prism:coverDate",
        "source": endpoint,
        "title": core.get("dc:title"),
        "doi": core.get("prism:doi"),
    }


def audit_microsoft(session: requests.Session, url: str) -> dict:
    match = MICROSOFT_PATH_RE.search(urlparse(url).path)
    if not match:
        return {"url": url, "unresolved_reason": "publication slug missing"}
    slug = normalized(match.group(1))
    endpoint = "https://api.openalex.org/works"
    response = None
    for attempt in range(4):
        response = session.get(
            endpoint,
            params={"search": slug, "per-page": 10},
            timeout=30,
        )
        if response.status_code != 429:
            break
        time.sleep(2 + attempt * 2)
    assert response is not None
    if response.status_code != 200:
        return {
            "url": url,
            "unresolved_reason": f"OpenAlex HTTP {response.status_code}",
            "source": response.url,
        }
    exact = [
        item
        for item in response.json().get("results", [])
        if normalized(item.get("display_name") or "") == slug
    ]
    exact_dates = {item.get("publication_date") for item in exact}
    exact_dates.discard(None)
    if len(exact) > 1 and len(exact_dates) == 1:
        exact = [exact[0]]
    if len(exact) != 1:
        candidates = [
            {
                "title": item.get("display_name"),
                "date": item.get("publication_date"),
                "id": item.get("id"),
                "normalized_title": normalized(item.get("display_name") or ""),
            }
            for item in response.json().get("results", [])[:5]
        ]
        return {
            "url": url,
            "unresolved_reason": f"expected one exact normalized-title match, found {len(exact)}",
            "source": response.url,
            "query_title": slug,
            "candidates": candidates,
        }
    work = exact[0]
    value = normalize_date(work.get("publication_date"))
    if not value:
        return {
            "url": url,
            "unresolved_reason": "exact OpenAlex match has no publication date",
            "source": work.get("id"),
        }
    return {
        "url": url,
        "status": "published",
        "date": value,
        "evidence": "OpenAlex exact normalized-title match",
        "source": work.get("id"),
        "title": work.get("display_name"),
        "doi": work.get("doi"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("io_links.md"))
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("scratch/publisher-metadata-continuation-audit.json"),
    )
    parser.add_argument(
        "--host",
        action="append",
        choices=["www.sciencedirect.com", "www.microsoft.com"],
        help="limit the audit to one or more hosts",
    )
    args = parser.parse_args()

    targets = []
    for line in args.input.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) != 3 or fields[1] != "indexed":
            continue
        host = urlparse(fields[0]).hostname
        wanted_hosts = set(args.host or ["www.sciencedirect.com", "www.microsoft.com"])
        if host in wanted_hosts:
            targets.append(fields[0])

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    results = []
    for index, url in enumerate(targets, 1):
        try:
            if urlparse(url).hostname == "www.sciencedirect.com":
                result = audit_sciencedirect(session, url)
                time.sleep(0.3)
            else:
                result = audit_microsoft(session, url)
                time.sleep(0.3)
        except Exception as error:
            result = {
                "url": url,
                "unresolved_reason": f"{type(error).__name__}: {error}",
            }
        results.append(result)
        if index % 20 == 0:
            time.sleep(1)
            print(
                f"{index}/{len(targets)} checked; "
                f"{sum(bool(item.get('date')) for item in results)} resolved",
                flush=True,
            )

    report = {
        "target_count": len(targets),
        "resolved_count": sum(bool(item.get("date")) for item in results),
        "unresolved_count": sum(not item.get("date") for item in results),
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

#!/usr/bin/env python3
"""Resolve undated CiteSeerX records by exact title-and-author OpenAlex matches."""

from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
from pathlib import Path

import requests


SOURCE = Path("scratch/citeseerx-continuation-audit.json")
REPORT = Path("scratch/citeseerx-openalex-audit.json")
CACHE = Path("tmp/citeseerx-continuation/openalex")
ENDPOINT = "https://api.openalex.org/works"


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def author_tokens(names: list[str]) -> set[str]:
    excluded = {"author", "authors", "department", "group", "university"}
    return {
        token
        for name in names
        for token in normalize(name).split()
        if len(token) > 1 and token not in excluded
    }


def fetch(session: requests.Session, title: str) -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{hashlib.sha256(normalize(title).encode()).hexdigest()}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    response = session.get(
        ENDPOINT,
        params={
            "search": title,
            "per-page": 10,
            "select": "id,doi,title,publication_year,publication_date,type,authorships",
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    path.write_text(
        json.dumps(payload, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    time.sleep(0.15)
    return payload


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    session = requests.Session()
    session.headers["User-Agent"] = (
        "io-links-date-audit/1.0 "
        "(https://github.com/alexyorke/alexyorke.github.io)"
    )
    results = []
    for item in source:
        if item.get("date"):
            continue
        records = item.get("candidate_records") or []
        record = next(
            (
                record
                for record in records
                if len(normalize(record.get("title", "")).split()) >= 3
            ),
            None,
        )
        if not record:
            continue
        names = [
            name
            for values in (item.get("candidate_authors") or {}).values()
            for name in values
        ]
        wanted_authors = author_tokens(names)
        result = {
            "url": item["url"],
            "status": None,
            "date": None,
            "source_title": record["title"],
            "source_authors": names,
        }
        try:
            payload = fetch(session, record["title"])
        except (requests.RequestException, ValueError) as exc:
            result["unresolved_reason"] = f"{type(exc).__name__}: {exc}"
            results.append(result)
            continue
        matches = []
        for work in payload.get("results", []):
            if normalize(work.get("title", "")) != normalize(record["title"]):
                continue
            names_openalex = [
                authorship.get("author", {}).get("display_name", "")
                for authorship in work.get("authorships", [])
            ]
            if wanted_authors and not (wanted_authors & author_tokens(names_openalex)):
                continue
            value = work.get("publication_date")
            if not value and work.get("publication_year"):
                value = str(work["publication_year"])
            if value:
                matches.append((work, value, names_openalex))
        distinct = {(work.get("id"), value) for work, value, _ in matches}
        if len(distinct) == 1:
            work, value, names_openalex = matches[0]
            result.update(
                status="publication",
                date=value,
                source=work.get("id"),
                evidence=(
                    "Exact normalized CiteSeerX title and author match in OpenAlex; "
                    f"title: {work.get('title')}; authors: {', '.join(names_openalex)}; "
                    f"publication date {value}; DOI {work.get('doi')}"
                ),
            )
        elif not matches:
            result["unresolved_reason"] = "No exact OpenAlex title-author match"
        else:
            result["unresolved_reason"] = "Multiple OpenAlex matches disagree"
        results.append(result)
    REPORT.write_text(
        json.dumps({"results": results}, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        {
            "checked": len(results),
            "resolved": sum(bool(item.get("date")) for item in results),
        }
    )


if __name__ == "__main__":
    main()

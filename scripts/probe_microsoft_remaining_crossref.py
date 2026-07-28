#!/usr/bin/env python3
"""Cache exact-title Crossref probes for remaining Microsoft Research URLs."""

from __future__ import annotations

import html
import json
import re
import time
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

import requests


INPUT = Path("io_links.md")
CACHE = Path("scratch/microsoft-remaining-crossref-cache.json")
ENDPOINT = "https://api.crossref.org/works"


def normalize(value: str) -> str:
    value = html.unescape(value)
    value = unicodedata.normalize("NFKD", value).lower()
    return " ".join(re.findall(r"[a-z0-9]+", value))


def title_from_url(url: str) -> str:
    slug = urlparse(url).path.split("/publication/", 1)[1].split("/", 1)[0]
    special = {
        "tackling-awkward-squad-monadic-inputoutput-concurrency-exceptions-foreign-language-calls-haskell":
            "Tackling the awkward squad: monadic input/output, concurrency, exceptions, and foreign-language calls in Haskell",
        "functional-programming-and-inputoutput":
            "Functional Programming and Input/Output",
    }
    return special.get(slug, slug.replace("-", " "))


def main() -> None:
    targets = []
    for line in INPUT.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) != 3 or fields[1] != "indexed":
            continue
        url = fields[0]
        if (
            urlparse(url).hostname == "www.microsoft.com"
            and "/research/publication/" in urlparse(url).path
        ):
            targets.append(url)

    session = requests.Session()
    session.headers["User-Agent"] = (
        "io-links-date-audit/1.0 (mailto:alexyorke@example.com)"
    )
    payload = {"endpoint": ENDPOINT, "targets": []}
    select = ",".join(
        [
            "DOI",
            "title",
            "published",
            "issued",
            "published-online",
            "published-print",
            "created",
            "container-title",
            "author",
            "URL",
            "type",
        ]
    )
    for url in targets:
        query_title = title_from_url(url)
        response = session.get(
            ENDPOINT,
            params={
                "query.title": query_title,
                "rows": 10,
                "select": select,
            },
            timeout=60,
        )
        response.raise_for_status()
        items = response.json()["message"]["items"]
        exact = [
            item
            for item in items
            if item.get("title")
            and normalize(item["title"][0]) == normalize(query_title)
        ]
        payload["targets"].append(
            {
                "url": url,
                "query_title": query_title,
                "request_url": response.url,
                "items": items,
                "exact": exact,
            }
        )
        print(f"{query_title}: {len(exact)} exact", flush=True)
        time.sleep(0.15)

    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()

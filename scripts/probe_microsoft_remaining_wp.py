#!/usr/bin/env python3
"""Cache exact-title Microsoft Research WordPress API probes."""

from __future__ import annotations

import html
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

import requests


INPUT = Path("io_links.md")
CACHE = Path("scratch/microsoft-remaining-wp-cache.json")
ENDPOINT = (
    "https://www.microsoft.com/en-us/research/wp-json/wp/v2/"
    "msr-research-item"
)


def normalize(value: str) -> str:
    value = html.unescape(value)
    value = unicodedata.normalize("NFKD", value).lower()
    return " ".join(re.findall(r"[a-z0-9]+", value))


def title_from_url(url: str) -> str:
    slug = urlparse(url).path.split("/publication/", 1)[1].split("/", 1)[0]
    return slug.replace("-", " ")


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
    session.headers["User-Agent"] = "io-links-date-audit/1.0"
    payload = {"endpoint": ENDPOINT, "targets": []}
    fields = "id,date,date_gmt,modified,slug,link,title"
    for url in targets:
        query_title = title_from_url(url)
        response = session.get(
            ENDPOINT,
            params={
                "search": query_title,
                "per_page": 100,
                "_fields": fields,
            },
            timeout=60,
        )
        response.raise_for_status()
        items = response.json()
        exact = [
            item
            for item in items
            if normalize(item["title"]["rendered"]) == normalize(query_title)
        ]
        payload["targets"].append(
            {
                "url": url,
                "query_title": query_title,
                "request_url": response.url,
                "response_headers": {
                    "x-wp-total": response.headers.get("X-WP-Total"),
                    "x-wp-totalpages": response.headers.get("X-WP-TotalPages"),
                },
                "items": items,
                "exact": exact,
            }
        )
        print(
            f"{query_title}: {len(items)} results, {len(exact)} exact",
            flush=True,
        )

    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()

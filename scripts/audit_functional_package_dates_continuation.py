#!/usr/bin/env python3
"""Audit indexed PureScript, Elm, and Libraries.io package pages."""

from __future__ import annotations

import json
import re
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

import requests


INPUT = Path("io_links.md")
RAW = Path("scratch/functional-package-dates-continuation-raw.json")
REPORT = Path("scratch/functional-package-dates-continuation-audit.json")
PUBLISHED_RE = re.compile(r"Published on (\d{4}-\d{2}-\d{2})T")
LATEST_RE = re.compile(
    r"Latest release ([A-Z][a-z]{2} \d{1,2}, \d{4})", re.IGNORECASE
)
FIRST_RE = re.compile(
    r"First release ([A-Z][a-z]{2} \d{1,2}, \d{4})", re.IGNORECASE
)


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def page_text(value: str) -> str:
    parser = TextExtractor()
    parser.feed(value)
    return " ".join(" ".join(parser.parts).split())


def human_date(value: str) -> str:
    return datetime.strptime(value, "%b %d, %Y").date().isoformat()


def main() -> None:
    targets = []
    for line in INPUT.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) != 3 or fields[1] != "indexed":
            continue
        if urlparse(fields[0]).hostname in {
            "pursuit.purescript.org",
            "package.elm-lang.org",
            "libraries.io",
        }:
            targets.append(fields[0])

    session = requests.Session()
    session.headers["User-Agent"] = "io-links-date-audit/1.0"
    cache: dict[str, tuple[int, str]] = {}
    raw_records = []
    results = []
    for url in targets:
        parsed = urlparse(url)
        parts = [unquote(part) for part in parsed.path.split("/") if part]
        endpoint = None
        pattern = None
        status = None
        evidence = None
        if parsed.hostname == "pursuit.purescript.org":
            if (
                len(parts) >= 3
                and parts[0] == "packages"
                and re.fullmatch(r"\d+(?:\.\d+)+", parts[2])
            ):
                endpoint = (
                    f"https://pursuit.purescript.org/packages/{parts[1]}/{parts[2]}"
                )
                pattern = PUBLISHED_RE
                status = "publication"
                evidence = "Pursuit exact package-version page explicit Published on timestamp."
        elif parsed.hostname == "package.elm-lang.org":
            if len(parts) >= 4 and parts[0] == "packages" and parts[3] == "latest":
                package = f"{parts[1]}/{parts[2]}"
                endpoint = f"https://libraries.io/elm/{quote(package, safe='')}"
                pattern = LATEST_RE
                status = "updated"
                evidence = "Libraries.io latest Elm release date for the package used by the latest documentation URL."
        elif parsed.hostname == "libraries.io":
            if len(parts) >= 2:
                endpoint = url
                pattern = FIRST_RE
                status = "created"
                evidence = "Libraries.io explicit first release date for the package."

        if not endpoint or not pattern or not status or not evidence:
            results.append(
                {
                    "url": url,
                    "unresolved_reason": "Search page, missing version, or unrecognized package page.",
                }
            )
            continue
        if endpoint not in cache:
            response = session.get(endpoint, timeout=40)
            cache[endpoint] = (
                response.status_code,
                page_text(response.text) if response.status_code == 200 else "",
            )
        status_code, text = cache[endpoint]
        raw_records.append(
            {
                "url": url,
                "endpoint": endpoint,
                "status_code": status_code,
                "text": text,
            }
        )
        match = pattern.search(text)
        if match:
            value = (
                match.group(1)
                if pattern is PUBLISHED_RE
                else human_date(match.group(1))
            )
            results.append(
                {
                    "url": url,
                    "status": status,
                    "date": value,
                    "evidence": evidence,
                    "source": endpoint,
                }
            )
        else:
            results.append(
                {
                    "url": url,
                    "unresolved_reason": (
                        f"Metadata page HTTP {status_code} has no applicable date."
                    ),
                    "source": endpoint,
                }
            )

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

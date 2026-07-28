#!/usr/bin/env python3
"""Audit indexed Hackage package/version/documentation links via upload times."""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests


INPUT = Path("io_links.md")
RAW = Path("scratch/hackage-upload-dates-continuation-raw.json")
REPORT = Path("scratch/hackage-upload-dates-continuation-audit.json")
VERSIONED_RE = re.compile(r"^.+-\d+(?:\.\d+)+(?:-\w+)?$")
UPLOADED_RE = re.compile(
    r"Uploaded by .+? at (\d{4}-\d{2}-\d{2})T", re.IGNORECASE
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


def package_target(url: str) -> tuple[str, bool] | None:
    parts = [unquote(part) for part in urlparse(url).path.split("/") if part]
    if len(parts) >= 4 and parts[0] == "packages" and parts[1] == "archive":
        name, version = parts[2:4]
        return f"{name}-{version}", True
    if len(parts) < 2 or parts[0] != "package":
        return None
    segment = parts[1]
    if segment.endswith(".tar.gz"):
        segment = segment[: -len(".tar.gz")]
    elif segment.endswith(".html"):
        segment = segment[: -len(".html")]
    if segment in {"packages", "Data.Array.IO", "Control.Monad.State", "GHC.IO"}:
        return None
    return segment, bool(VERSIONED_RE.fullmatch(segment))


def main() -> None:
    targets = []
    for line in INPUT.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) != 3 or fields[1] != "indexed":
            continue
        if urlparse(fields[0]).hostname in {
            "hackage.haskell.org",
            "hackage-content.haskell.org",
        }:
            targets.append(fields[0])

    session = requests.Session()
    session.headers["User-Agent"] = "io-links-date-audit/1.0"
    cache: dict[str, tuple[int, str]] = {}
    raw_records = []
    results = []
    for url in targets:
        target = package_target(url)
        if not target:
            results.append(
                {
                    "url": url,
                    "unresolved_reason": "Hackage index/tag/API page or unrecognized legacy package path.",
                }
            )
            continue
        package, exact_version = target
        endpoint = f"https://hackage.haskell.org/package/{package}"
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
        match = UPLOADED_RE.search(text)
        if match:
            results.append(
                {
                    "url": url,
                    "status": "uploaded" if exact_version else "updated",
                    "date": match.group(1),
                    "evidence": (
                        "Hackage exact package-version upload timestamp."
                        if exact_version
                        else "Hackage latest package-version upload timestamp for the versionless page."
                    ),
                    "source": endpoint,
                    "package": package,
                }
            )
        else:
            results.append(
                {
                    "url": url,
                    "unresolved_reason": (
                        f"Hackage HTTP {status_code} has no explicit upload timestamp."
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

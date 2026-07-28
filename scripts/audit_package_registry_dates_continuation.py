#!/usr/bin/env python3
"""Audit indexed Packagist package pages and pub.dev latest documentation."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

import requests


INPUT = Path("io_links.md")
RAW = Path("scratch/package-registry-dates-continuation-raw.json")
REPORT = Path("scratch/package-registry-dates-continuation-audit.json")


def packagist_name(url: str) -> str | None:
    parts = [part for part in urlparse(url).path.split("/") if part]
    if len(parts) == 3 and parts[0] == "packages":
        return f"{parts[1]}/{parts[2]}"
    return None


def pub_name(url: str) -> str | None:
    parts = [part for part in urlparse(url).path.split("/") if part]
    if len(parts) >= 3 and parts[0] == "documentation" and parts[2] == "latest":
        return parts[1]
    return None


def main() -> None:
    targets = []
    for line in INPUT.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) != 3 or fields[1] != "indexed":
            continue
        host = urlparse(fields[0]).hostname
        if host in {"packagist.org", "pub.dev"}:
            targets.append(fields[0])

    session = requests.Session()
    session.headers["User-Agent"] = "io-links-date-audit/1.0"
    raw_records = []
    results = []
    packagist_cache: dict[str, tuple[str, object]] = {}
    pub_cache: dict[str, tuple[str, object]] = {}

    for url in targets:
        host = urlparse(url).hostname
        if host == "packagist.org":
            name = packagist_name(url)
            if not name:
                results.append(
                    {
                        "url": url,
                        "unresolved_reason": "Mutable vendor/package index page has no single creation date.",
                    }
                )
                continue
            endpoint = f"https://repo.packagist.org/p2/{name}.json"
            if name not in packagist_cache:
                response = session.get(endpoint, timeout=30)
                payload = (
                    response.json()
                    if response.headers.get("content-type", "").startswith(
                        "application/json"
                    )
                    else response.text
                )
                packagist_cache[name] = (str(response.status_code), payload)
            status_code, payload = packagist_cache[name]
            raw_records.append(
                {
                    "url": url,
                    "endpoint": endpoint,
                    "status_code": status_code,
                    "body": payload,
                }
            )
            versions = (
                payload.get("packages", {}).get(name, [])
                if isinstance(payload, dict)
                else []
            )
            timestamps = sorted(
                value
                for item in versions
                for value in [item.get("published-time") or item.get("time")]
                if value
            )
            if timestamps:
                results.append(
                    {
                        "url": url,
                        "status": "created",
                        "date": timestamps[0][:10],
                        "evidence": "Packagist package metadata earliest published release timestamp.",
                        "source": endpoint,
                        "package": name,
                    }
                )
            else:
                results.append(
                    {
                        "url": url,
                        "unresolved_reason": (
                            f"Packagist metadata HTTP {status_code} has no release timestamps."
                        ),
                        "source": endpoint,
                    }
                )
        else:
            name = pub_name(url)
            if not name:
                results.append(
                    {
                        "url": url,
                        "unresolved_reason": "pub.dev URL is not a latest-version documentation page.",
                    }
                )
                continue
            endpoint = f"https://pub.dev/api/packages/{name}"
            if name not in pub_cache:
                response = session.get(endpoint, timeout=30)
                payload = (
                    response.json()
                    if response.headers.get("content-type", "").startswith(
                        "application/json"
                    )
                    else response.text
                )
                pub_cache[name] = (str(response.status_code), payload)
            status_code, payload = pub_cache[name]
            raw_records.append(
                {
                    "url": url,
                    "endpoint": endpoint,
                    "status_code": status_code,
                    "body": payload,
                }
            )
            published = (
                payload.get("latest", {}).get("published")
                if isinstance(payload, dict)
                else None
            )
            if published:
                results.append(
                    {
                        "url": url,
                        "status": "updated",
                        "date": published[:10],
                        "evidence": "pub.dev API publication timestamp for the current latest documentation version.",
                        "source": endpoint,
                        "package": name,
                        "version": payload.get("latest", {}).get("version"),
                    }
                )
            else:
                results.append(
                    {
                        "url": url,
                        "unresolved_reason": (
                            f"pub.dev metadata HTTP {status_code} has no latest publication timestamp."
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

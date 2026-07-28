#!/usr/bin/env python3
"""Audit indexed npm, unpkg, and Skypack package links via npm registry."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

import requests


INPUT = Path("io_links.md")
RAW = Path("scratch/npm-registry-dates-continuation-raw.json")
REPORT = Path("scratch/npm-registry-dates-continuation-audit.json")
HOSTS = {"www.npmjs.com", "npm.io", "app.unpkg.com", "www.skypack.dev"}


def target_package(url: str) -> tuple[str, str | None, str] | None:
    parsed = urlparse(url)
    parts = [unquote(part) for part in parsed.path.split("/") if part]
    if parsed.hostname == "www.npmjs.com":
        if len(parts) < 2 or parts[0] != "package":
            return None
        name = "/".join(parts[1:3]) if parts[1].startswith("@") else parts[1]
        return name, None, "created"
    if parsed.hostname == "npm.io":
        if len(parts) < 2 or parts[0] != "package":
            return None
        return "/".join(parts[1:]), None, "created"
    if parsed.hostname == "www.skypack.dev":
        if len(parts) < 2 or parts[0] != "view":
            return None
        return "/".join(parts[1:]), None, "created"
    if parsed.hostname == "app.unpkg.com":
        if not parts:
            return None
        segment = parts[0]
        if segment.startswith("@"):
            if len(parts) < 2:
                return None
            segment = f"{segment}/{parts[1]}"
        if "@" in segment[1:]:
            name, version = segment.rsplit("@", 1)
            return name, version, "uploaded"
        return segment, None, "latest"
    return None


def main() -> None:
    targets = []
    for line in INPUT.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if (
            len(fields) == 3
            and fields[1] == "indexed"
            and urlparse(fields[0]).hostname in HOSTS
        ):
            targets.append(fields[0])

    session = requests.Session()
    session.headers["User-Agent"] = "io-links-date-audit/1.0"
    cache: dict[str, tuple[int, object]] = {}
    raw_records = []
    results = []
    for url in targets:
        target = target_package(url)
        if not target:
            results.append(
                {
                    "url": url,
                    "unresolved_reason": "Mutable search/index page or unrecognized package URL.",
                }
            )
            continue
        package, version, mode = target
        endpoint = f"https://registry.npmjs.org/{quote(package, safe='')}"
        if endpoint not in cache:
            response = session.get(endpoint, timeout=30)
            payload = (
                response.json()
                if response.headers.get("content-type", "").startswith(
                    "application/json"
                )
                else response.text
            )
            cache[endpoint] = (response.status_code, payload)
        status_code, payload = cache[endpoint]
        raw_records.append(
            {
                "url": url,
                "package": package,
                "requested_version": version,
                "endpoint": endpoint,
                "status_code": status_code,
                "body": payload,
            }
        )
        timestamp = None
        status = None
        evidence = None
        if isinstance(payload, dict):
            times = payload.get("time", {})
            if mode == "created":
                timestamp = times.get("created")
                status = "created"
                evidence = "npm registry package creation timestamp."
            elif mode == "uploaded":
                timestamp = times.get(version)
                status = "uploaded"
                evidence = "npm registry exact version publication timestamp."
            else:
                latest = payload.get("dist-tags", {}).get("latest")
                timestamp = times.get(latest)
                status = "updated"
                evidence = (
                    "npm registry publication timestamp for the current latest version."
                )
        if timestamp and status and evidence:
            results.append(
                {
                    "url": url,
                    "status": status,
                    "date": timestamp[:10],
                    "evidence": evidence,
                    "source": endpoint,
                    "package": package,
                    "version": version,
                }
            )
        else:
            results.append(
                {
                    "url": url,
                    "unresolved_reason": (
                        f"npm registry HTTP {status_code} has no applicable timestamp."
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

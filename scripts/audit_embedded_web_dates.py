#!/usr/bin/env python3
"""Resolve indexed web pages from explicit embedded or HTTP date metadata."""

from __future__ import annotations

import concurrent.futures
import argparse
import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import unquote, urlparse
from zoneinfo import ZoneInfo

import requests
from dateutil import parser as date_parser


INPUT = Path("io_links.md")
REPORT = Path("scratch/embedded-web-dates-audit.json")
CACHE = Path("tmp/http-date-cache")
MAX_BYTES = 4 * 1024 * 1024
DATE_KEYS = {
    "article:published_time": "published",
    "article:modified_time": "modified",
    "citation_date": "publication",
    "citation_online_date": "publication",
    "citation_publication_date": "publication",
    "citation_cover_date": "publication",
    "dc.date": "publication",
    "dc.date.created": "created",
    "dc.date.issued": "publication",
    "dc.date.modified": "modified",
    "dcterms.created": "created",
    "dcterms.date": "publication",
    "dcterms.issued": "publication",
    "dcterms.modified": "modified",
    "datecreated": "created",
    "datemodified": "modified",
    "datepublished": "published",
    "og:published_time": "published",
    "publish-date": "published",
    "pubdate": "published",
}
ATTR_RE = re.compile(
    r"""(?P<key>[A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*
        (?P<quote>["'])(?P<value>.*?)(?P=quote)""",
    re.X | re.S,
)
TAG_RE = re.compile(r"<(?:meta|time)\b[^>]*>", re.I | re.S)
JSON_DATE_RE = re.compile(
    r"""["'](?P<key>datePublished|dateCreated|dateModified)["']\s*:\s*
        ["'](?P<value>[^"']+)["']""",
    re.I | re.X,
)
URL_DATE_RE = re.compile(
    r"(?<!\d)(?P<year>19\d{2}|20\d{2})[/-](?P<month>0?[1-9]|1[0-2])"
    r"(?:[/-](?P<day>0?[1-9]|[12]\d|3[01]))?(?!\d)"
)


def normalize(raw: str) -> str | None:
    raw = raw.strip()
    try:
        parsed = date_parser.parse(raw, fuzzy=False)
    except (OverflowError, ValueError):
        return None
    value = parsed.date()
    if value.year < 1980 or value > date.today():
        return None
    has_day = bool(
        re.search(r"(?:^|\D)(?:0?[1-9]|[12]\d|3[01])(?:\D|$)", raw)
    )
    has_month = bool(
        re.search(
            r"(?:^|\D)(?:0?[1-9]|1[0-2])(?:\D|$)|"
            r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)",
            raw,
            re.I,
        )
    )
    if has_day and has_month:
        return value.isoformat()
    if has_month:
        return f"{value.year:04d}-{value.month:02d}"
    return f"{value.year:04d}"


def embedded_date(text: str) -> tuple[str, str, str] | None:
    candidates: list[tuple[int, str, str, str]] = []
    priority = {"published": 0, "publication": 1, "created": 2, "modified": 3}
    for tag in TAG_RE.findall(text):
        attrs = {
            match.group("key").casefold(): match.group("value")
            for match in ATTR_RE.finditer(tag)
        }
        key = (
            attrs.get("property")
            or attrs.get("name")
            or attrs.get("itemprop")
            or ""
        ).casefold()
        status = DATE_KEYS.get(key)
        raw = attrs.get("content") or attrs.get("datetime")
        if status and raw and (value := normalize(raw)):
            candidates.append((priority[status], status, value, f"{key}={raw}"))
    for match in JSON_DATE_RE.finditer(text):
        key = match.group("key").casefold()
        status = DATE_KEYS[key]
        raw = match.group("value")
        if value := normalize(raw):
            candidates.append((priority[status], status, value, f"{key}={raw}"))
    if not candidates:
        return None
    _, status, value, evidence = min(candidates)
    return status, value, evidence


def cache_paths(url: str) -> tuple[Path, Path]:
    stem = hashlib.sha256(url.encode()).hexdigest()
    return CACHE / f"{stem}.body", CACHE / f"{stem}.json"


def fetch(url: str) -> tuple[bytes, dict]:
    body_path, meta_path = cache_paths(url)
    if body_path.exists() and meta_path.exists():
        return body_path.read_bytes(), json.loads(meta_path.read_text(encoding="utf-8"))
    response = requests.get(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; io-links-date-audit/1.0; "
                "+https://github.com/alexyorke/alexyorke.github.io)"
            )
        },
        timeout=25,
        stream=True,
        allow_redirects=True,
    )
    chunks = []
    size = 0
    for chunk in response.iter_content(65_536):
        size += len(chunk)
        if size > MAX_BYTES:
            break
        chunks.append(chunk)
    body = b"".join(chunks)
    meta = {
        "status_code": response.status_code,
        "url": response.url,
        "headers": dict(response.headers),
        "truncated": size > MAX_BYTES,
    }
    body_path.write_bytes(body)
    meta_path.write_text(
        json.dumps(meta, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return body, meta


def inspect(url: str, allow_http_last_modified: bool = True) -> dict:
    item = {"url": url, "status": None, "date": None}
    parsed = urlparse(url)
    url_match = URL_DATE_RE.search(unquote(parsed.path))
    if url_match:
        year = int(url_match.group("year"))
        month = int(url_match.group("month"))
        day = url_match.group("day")
        try:
            value = date(year, month, int(day or 1))
        except ValueError:
            pass
        else:
            item.update(
                status="published",
                date=value.isoformat() if day else f"{year:04d}-{month:02d}",
                source="url-path",
                evidence=f"Explicit calendar date in URL path: {url_match.group(0)}",
            )
            return item
    try:
        body, meta = fetch(url)
        item.update(
            http_status=meta["status_code"],
            final_url=meta["url"],
            cache=str(cache_paths(url)[0]),
        )
        content_type = meta["headers"].get("Content-Type", "")
        if (
            parsed.hostname != "dblp.org"
            and ("html" in content_type.casefold() or body.lstrip().startswith(b"<"))
        ):
            text = body.decode("utf-8", errors="replace")
            if result := embedded_date(text):
                status, value, evidence = result
                item.update(
                    status=status,
                    date=value,
                    source=meta["url"],
                    evidence=f"Embedded metadata {evidence}",
                )
                return item
        raw_modified = meta["headers"].get("Last-Modified")
        if allow_http_last_modified and raw_modified and meta["status_code"] < 400:
            modified = parsedate_to_datetime(raw_modified)
            if modified.tzinfo is None:
                modified = modified.replace(tzinfo=timezone.utc)
            local_today = datetime.now(ZoneInfo("America/Los_Angeles")).date()
            if (
                datetime(1980, 1, 1, tzinfo=timezone.utc) <= modified
                and modified.date() < local_today - timedelta(days=1)
            ):
                item.update(
                    status="modified",
                    date=modified.date().isoformat(),
                    source=meta["url"],
                    evidence=f"HTTP Last-Modified: {raw_modified}",
                )
                return item
        item["unresolved_reason"] = "No explicit embedded or HTTP date metadata."
    except Exception as exc:
        item["unresolved_reason"] = f"{type(exc).__name__}: {exc}"
    return item


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--current-status",
        action="append",
        default=[],
        help="Current row status to audit; may be supplied more than once.",
    )
    parser.add_argument("--date-from")
    parser.add_argument("--date-to")
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument(
        "--no-http-last-modified",
        action="store_true",
        help="Use embedded content dates only; ignore HTTP Last-Modified headers.",
    )
    args = parser.parse_args()
    if not args.current_status:
        args.current_status = ["indexed"]
    CACHE.mkdir(parents=True, exist_ok=True)
    targets = []
    for line in INPUT.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) != 3 or fields[1] not in set(args.current_status):
            continue
        if args.date_from and fields[2] < args.date_from:
            continue
        if args.date_to and fields[2] > args.date_to:
            continue
        parsed = urlparse(fields[0])
        if parsed.scheme not in {"http", "https"}:
            continue
        if re.search(r"\.(?:pdf|ps|ps\.gz)(?:$|[?#])", parsed.path, re.I):
            continue
        targets.append(fields[0])
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        futures = {
            pool.submit(inspect, url, not args.no_http_last_modified): url
            for url in targets
        }
        for count, future in enumerate(concurrent.futures.as_completed(futures), 1):
            results.append(future.result())
            if count % 100 == 0 or count == len(futures):
                resolved = sum(bool(item.get("date")) for item in results)
                print(f"{count}/{len(futures)} checked; {resolved} dated", flush=True)
    payload = {
        "target_count": len(results),
        "resolved_count": sum(bool(item.get("date")) for item in results),
        "unresolved_count": sum(not item.get("date") for item in results),
        "results": sorted(results, key=lambda item: item["url"]),
    }
    args.report.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print({key: value for key, value in payload.items() if key.endswith("_count")})


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Fill missing dates in io_links.md from explicit, source-backed metadata.

The script deliberately ignores HTTP Last-Modified headers and generic copyright
years: those usually describe the hosting page, not the linked item.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import difflib
import gzip
import hashlib
import html
import json
import re
import sys
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, quote, unquote, urlparse

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser


USER_AGENT = (
    "io-links-date-enricher/1.0 "
    "(scholarly metadata maintenance; https://github.com/alexyorke/alexyorke.github.io)"
)
MAX_BODY_BYTES = 2_000_000
DATE_KEYS = {
    "citation_publication_date": "publication",
    "citation_date": "publication",
    "citation_online_date": "published",
    "dc.date.issued": "publication",
    "dcterms.issued": "publication",
    "prism.publicationdate": "publication",
    "article:published_time": "published",
    "og:published_time": "published",
    "datepublished": "published",
    "uploaddate": "uploaded",
    "datemodified": "modified",
    "article:modified_time": "modified",
    "og:updated_time": "updated",
    "lastmod": "modified",
}
DATE_KEY_PRIORITY = list(DATE_KEYS)
DATEISH_RE = re.compile(
    r"(?<!\d)(?P<year>18\d{2}|19\d{2}|20\d{2})"
    r"(?:[-/.](?P<month>1[0-2]|0?[1-9])"
    r"(?:[-/.](?P<day>3[01]|[12]\d|0?[1-9]))?)?"
)
DOI_RE = re.compile(
    r"(?:doi\.org/|/doi/(?:abs/|pdf/)?)(10\.\d{4,9}/[^?#\s]+)", re.I
)
STACKEXCHANGE_RE = re.compile(
    r"https?://(?P<host>[^/]*stack(?:overflow|exchange)\.com)/questions/(?P<id>\d+)",
    re.I,
)
STACKANSWER_RE = re.compile(
    r"https?://(?P<host>[^/]*stack(?:overflow|exchange)\.com)/a/(?P<id>\d+)",
    re.I,
)
REDDIT_RE = re.compile(r"reddit\.com/r/[^/]+/comments/(?P<id>[a-z0-9]+)", re.I)
HACKAGE_RE = re.compile(
    r"https?://(?:hackage(?:-content)?\.haskell\.org)/(?:package/)?"
    r"(?P<package>[A-Za-z0-9][A-Za-z0-9_.+-]*-\d[^/?#]*)",
    re.I,
)
GITHUB_REPO_RE = re.compile(
    r"https?://github\.com/(?P<owner>[^/?#]+)/(?P<repo>[^/?#]+?)(?:\.git)?/?(?:[?#].*)?$",
    re.I,
)
_CACHE_LOCKS: dict[str, threading.Lock] = {}
_CACHE_LOCKS_GUARD = threading.Lock()


@dataclass(frozen=True)
class Resolution:
    url: str
    status: str | None
    date: str | None
    source: str
    confidence: str
    detail: str = ""
    http_status: int | None = None


def normalize_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        parts = value.get("date-parts")
        if isinstance(parts, list) and parts and isinstance(parts[0], list):
            return format_parts(parts[0])
        return None
    if isinstance(value, list):
        if value and all(isinstance(x, int) for x in value):
            return format_parts(value)
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, timezone.utc).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return None

    text = str(value).strip()
    if not text:
        return None
    if re.search(
        r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
        r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|"
        r"Nov(?:ember)?|Dec(?:ember)?)\b",
        text,
        re.I,
    ):
        try:
            return date_parser.parse(text, fuzzy=True).date().isoformat()
        except (ValueError, OverflowError):
            pass
    match = DATEISH_RE.search(text)
    if not match:
        return None
    year = int(match.group("year"))
    month_text = match.group("month")
    day_text = match.group("day")
    if not month_text:
        return f"{year:04d}"
    month = int(month_text)
    if not day_text:
        return f"{year:04d}-{month:02d}"
    day = int(day_text)
    try:
        return datetime(year, month, day).date().isoformat()
    except ValueError:
        return None


def format_parts(parts: Iterable[int]) -> str | None:
    values = list(parts)
    if not values:
        return None
    if len(values) == 1:
        return f"{values[0]:04d}"
    if len(values) == 2:
        return f"{values[0]:04d}-{values[1]:02d}"
    try:
        return datetime(values[0], values[1], values[2]).date().isoformat()
    except ValueError:
        return None


def cache_path(cache_dir: Path, url: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return cache_dir / digest[:2] / f"{digest}.json.gz"


def cache_lock(url: str) -> threading.Lock:
    with _CACHE_LOCKS_GUARD:
        return _CACHE_LOCKS.setdefault(url, threading.Lock())


def load_cached(cache_dir: Path, url: str) -> dict[str, Any] | None:
    path = cache_path(cache_dir, url)
    if not path.exists():
        return None
    try:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def store_cached(cache_dir: Path, url: str, payload: dict[str, Any]) -> None:
    path = cache_path(cache_dir, url)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    with gzip.open(temp, "wt", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False)
    temp.replace(path)


def fetch(
    session: requests.Session, cache_dir: Path, url: str, timeout: float
) -> dict[str, Any]:
    with cache_lock(url):
        cached = load_cached(cache_dir, url)
        if cached is not None and cached.get("status") is not None:
            return cached
        try:
            response = session.get(
                url,
                timeout=timeout,
                allow_redirects=True,
                stream=True,
                headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
            )
            chunks: list[bytes] = []
            body_size = 0
            truncated = False
            for chunk in response.iter_content(chunk_size=65_536):
                if not chunk:
                    continue
                remaining = MAX_BODY_BYTES - body_size
                if remaining <= 0:
                    truncated = True
                    break
                chunks.append(chunk[:remaining])
                body_size += min(len(chunk), remaining)
                if len(chunk) > remaining:
                    truncated = True
                    break
            body = b"".join(chunks)
            payload = {
                "requested_url": url,
                "final_url": response.url,
                "status": response.status_code,
                "headers": dict(response.headers),
                "body_hex": body.hex(),
                "truncated": truncated,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
        except requests.RequestException as exc:
            payload = {
                "requested_url": url,
                "status": None,
                "error": f"{type(exc).__name__}: {exc}",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
        store_cached(cache_dir, url, payload)
        return payload


def fetch_head(
    session: requests.Session, cache_dir: Path, url: str, timeout: float
) -> dict[str, Any]:
    cache_url = f"HEAD {url}"
    cached = load_cached(cache_dir, cache_url)
    if cached is not None and cached.get("status") is not None:
        return cached
    with cache_lock(cache_url):
        cached = load_cached(cache_dir, cache_url)
        if cached is not None and cached.get("status") is not None:
            return cached
        try:
            response = session.head(
                url,
                timeout=timeout,
                allow_redirects=True,
                headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
            )
            payload = {
                "requested_url": url,
                "final_url": response.url,
                "status": response.status_code,
                "headers": dict(response.headers),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
        except requests.RequestException as exc:
            payload = {
                "requested_url": url,
                "status": None,
                "error": f"{type(exc).__name__}: {exc}",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
        store_cached(cache_dir, cache_url, payload)
        return payload


def fetch_range(
    session: requests.Session, cache_dir: Path, url: str, timeout: float
) -> dict[str, Any]:
    cache_url = f"RANGE {url}"
    cached = load_cached(cache_dir, cache_url)
    if cached is not None and cached.get("status") is not None:
        return cached
    with cache_lock(cache_url):
        cached = load_cached(cache_dir, cache_url)
        if cached is not None and cached.get("status") is not None:
            return cached
        try:
            response = session.get(
                url,
                timeout=timeout,
                allow_redirects=True,
                stream=True,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "*/*",
                    "Range": "bytes=0-524287",
                },
            )
            chunks: list[bytes] = []
            size = 0
            for chunk in response.iter_content(chunk_size=65_536):
                if not chunk:
                    continue
                remaining = 524_288 - size
                if remaining <= 0:
                    break
                chunks.append(chunk[:remaining])
                size += min(len(chunk), remaining)
            payload = {
                "requested_url": url,
                "final_url": response.url,
                "status": response.status_code,
                "headers": dict(response.headers),
                "body_hex": b"".join(chunks).hex(),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
        except requests.RequestException as exc:
            payload = {
                "requested_url": url,
                "status": None,
                "error": f"{type(exc).__name__}: {exc}",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
        store_cached(cache_dir, cache_url, payload)
        return payload


def response_body(payload: dict[str, Any]) -> bytes:
    try:
        return bytes.fromhex(payload.get("body_hex", ""))
    except ValueError:
        return b""


def json_date_candidates(node: Any) -> list[tuple[str, Any]]:
    found: list[tuple[str, Any]] = []
    if isinstance(node, dict):
        lowered = {str(key).lower(): value for key, value in node.items()}
        for key in DATE_KEY_PRIORITY:
            if key in lowered:
                found.append((key, lowered[key]))
        for value in node.values():
            found.extend(json_date_candidates(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(json_date_candidates(item))
    return found


def explicit_html_date(
    html: bytes, url: str, *, allow_jsonld: bool = True
) -> Resolution | None:
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[tuple[str, str, str]] = []

    for tag in soup.find_all("meta"):
        key = (
            tag.get("name")
            or tag.get("property")
            or tag.get("itemprop")
            or ""
        ).strip().lower()
        content = (tag.get("content") or "").strip()
        if key in DATE_KEYS and content:
            candidates.append((key, content, f"meta:{key}"))

    for tag in soup.find_all("time"):
        key = (tag.get("itemprop") or "").strip().lower()
        value = (tag.get("datetime") or tag.get_text(" ", strip=True)).strip()
        if key in DATE_KEYS and value:
            candidates.append((key, value, f"time:{key}"))

    if allow_jsonld:
        for tag in soup.find_all(
            "script", attrs={"type": re.compile("ld\\+json", re.I)}
        ):
            try:
                node = json.loads(tag.string or tag.get_text())
            except (json.JSONDecodeError, TypeError):
                continue
            for key, value in json_date_candidates(node):
                if isinstance(value, (str, int, float)):
                    candidates.append((key, str(value), f"json-ld:{key}"))

    by_key: dict[str, list[tuple[str, str]]] = {}
    for key, value, detail in candidates:
        by_key.setdefault(key, []).append((value, detail))
    for key in DATE_KEY_PRIORITY:
        for value, detail in by_key.get(key, []):
            date = normalize_date(value)
            if date:
                return Resolution(
                    url, DATE_KEYS[key], date, "page-metadata", "high", detail
                )
    return None


def crossref_resolution(
    session: requests.Session, cache_dir: Path, url: str, timeout: float
) -> Resolution | None:
    match = DOI_RE.search(unquote(url))
    if not match:
        return None
    doi = match.group(1).rstrip("./")
    api_url = f"https://api.crossref.org/works/{quote(doi, safe='')}"
    payload = fetch(session, cache_dir, api_url, timeout)
    if payload.get("status") != 200:
        return None
    try:
        message = json.loads(response_body(payload)).get("message", {})
    except json.JSONDecodeError:
        return None
    for key in ("published", "published-online", "published-print", "issued"):
        date = normalize_date(message.get(key))
        if date:
            return Resolution(
                url,
                "publication",
                date,
                "crossref",
                "high",
                f"{key}; DOI {doi}",
                payload.get("status"),
            )
    return None


def stackexchange_resolution(
    session: requests.Session, cache_dir: Path, url: str, timeout: float
) -> Resolution | None:
    answer_match = STACKANSWER_RE.search(url)
    if answer_match:
        payload = fetch(session, cache_dir, url, timeout)
        if payload.get("status") != 200:
            return None
        soup = BeautifulSoup(response_body(payload), "html.parser")
        answer = soup.select_one(f'[data-answerid="{answer_match.group("id")}"]')
        dated = answer.select_one('time[itemprop="dateCreated"]') if answer else None
        date = (
            normalize_date(dated.get("datetime") or dated.get_text())
            if dated
            else None
        )
        if date:
            return Resolution(
                url,
                "created",
                date,
                "stackexchange-page",
                "high",
                f"answer {answer_match.group('id')} creation timestamp",
                payload.get("status"),
            )
        return None

    match = STACKEXCHANGE_RE.search(url)
    if not match:
        return None
    host = match.group("host").lower()
    if host.endswith("stackoverflow.com"):
        service = "stackoverflow"
    else:
        service = host.removesuffix(".com")
    stackprinter_url = (
        "https://www.stackprinter.com/export"
        f"?question={match.group('id')}&service={quote(service)}"
        "&language=en&hideAnswers=true&showAll=false&width=640"
    )
    payload = fetch(session, cache_dir, stackprinter_url, timeout)
    if payload.get("status") != 200:
        return None
    soup = BeautifulSoup(response_body(payload), "html.parser")
    details = " ".join(
        node.get_text(" ", strip=True) for node in soup.select(".question-details")
    )
    date_match = re.search(r"\[(\d{4}-\d{2}-\d{2})(?:\s[^\]]*)?\]", details)
    date = normalize_date(date_match.group(1)) if date_match else None
    if date:
        return Resolution(
            url,
            "created",
            date,
            "stackprinter",
            "high",
            f"question {match.group('id')} creation timestamp",
            payload.get("status"),
        )
    return None


def reddit_resolution(
    session: requests.Session, cache_dir: Path, url: str, timeout: float
) -> Resolution | None:
    match = REDDIT_RE.search(url)
    if not match:
        return None
    parsed = urlparse(url)
    rss_path = parsed.path.rstrip("/") + "/.rss"
    rss_url = f"https://www.reddit.com{rss_path}"
    payload = fetch(session, cache_dir, rss_url, timeout)
    if payload.get("status") != 200:
        return None
    body = response_body(payload).decode("utf-8", errors="replace")
    published = re.search(r"<published>([^<]+)</published>", body, re.I)
    date = normalize_date(published.group(1)) if published else None
    if date:
        return Resolution(
            url,
            "created",
            date,
            "reddit-rss",
            "high",
            f"submission {match.group('id')} published timestamp",
            payload.get("status"),
        )
    return None


def normalized_title(value: str) -> str:
    value = html.unescape(value)
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def title_similarity(left: str, right: str) -> float:
    left_normalized = normalized_title(left)
    right_normalized = normalized_title(right)
    sequence = difflib.SequenceMatcher(
        None, left_normalized, right_normalized
    ).ratio()
    left_tokens = set(left_normalized.split())
    right_tokens = set(right_normalized.split())
    union = left_tokens | right_tokens
    jaccard = len(left_tokens & right_tokens) / len(union) if union else 0.0
    return max(sequence, jaccard)


def researchgate_title(url: str) -> str | None:
    if "researchgate.net" not in urlparse(url).netloc.lower():
        return None
    match = re.search(r"/publication/\d+_(?P<title>[^/?#]+)", unquote(url), re.I)
    if not match:
        return None
    title = re.sub(r"[_-]+", " ", match.group("title")).strip()
    return title if len(title.split()) >= 3 else None


def scholarly_title_resolution(
    session: requests.Session, cache_dir: Path, url: str, timeout: float
) -> Resolution | None:
    title = researchgate_title(url)
    if not title:
        return None
    target = normalized_title(title)
    openalex_url = (
        "https://api.openalex.org/works"
        f"?search={quote(title)}&per-page=5&select=title,publication_date,publication_year"
    )
    payload = fetch(session, cache_dir, openalex_url, timeout)
    if payload.get("status") == 200:
        try:
            results = json.loads(response_body(payload)).get("results", [])
        except json.JSONDecodeError:
            results = []
        for item in results:
            similarity = title_similarity(title, item.get("title", ""))
            if similarity < 0.92:
                continue
            date = normalize_date(
                item.get("publication_date") or item.get("publication_year")
            )
            if date:
                return Resolution(
                    url,
                    "publication",
                    date,
                    "openalex-title",
                    "high" if similarity == 1.0 else "medium",
                    f"title similarity {similarity:.3f}: {item.get('title')}",
                    payload.get("status"),
                )

    crossref_url = (
        "https://api.crossref.org/works"
        f"?query.title={quote(title)}&rows=5"
        "&select=title,published,published-online,published-print,issued,DOI"
    )
    payload = fetch(session, cache_dir, crossref_url, timeout)
    if payload.get("status") != 200:
        return None
    try:
        items = json.loads(response_body(payload)).get("message", {}).get("items", [])
    except json.JSONDecodeError:
        return None
    for item in items:
        item_titles = item.get("title") or []
        if not item_titles:
            continue
        similarity = title_similarity(title, item_titles[0])
        if similarity < 0.92:
            continue
        for key in ("published", "published-online", "published-print", "issued"):
            date = normalize_date(item.get(key))
            if date:
                return Resolution(
                    url,
                    "publication",
                    date,
                    "crossref-title",
                    "high" if similarity == 1.0 else "medium",
                    f"title similarity {similarity:.3f}; {key}; "
                    f"DOI {item.get('DOI', 'N/A')}",
                    payload.get("status"),
                )
    return None


def community_page_resolution(
    session: requests.Session, cache_dir: Path, url: str, timeout: float
) -> Resolution | None:
    host = urlparse(url).netloc.lower()
    supported = {
        "news.ycombinator.com",
        "www.mail-archive.com",
        "mailman.haskell.org",
        "pkg.go.dev",
    }
    if host not in supported:
        return None
    if host == "news.ycombinator.com":
        item_id = (parse_qs(urlparse(url).query).get("id") or [None])[0]
        if not item_id or not item_id.isdigit():
            return None
        api_url = f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json"
        payload = fetch(session, cache_dir, api_url, timeout)
        if payload.get("status") != 200:
            return None
        try:
            item = json.loads(response_body(payload))
        except json.JSONDecodeError:
            return None
        date = normalize_date(item.get("time")) if isinstance(item, dict) else None
        if date:
            return Resolution(
                url,
                "created",
                date,
                "hacker-news-api",
                "high",
                f"item {item_id} creation timestamp",
                payload.get("status"),
            )
        return None
    payload = fetch(session, cache_dir, url, timeout)
    if payload.get("status") != 200:
        return None
    soup = BeautifulSoup(response_body(payload), "html.parser")
    value: str | None = None
    status = "created"
    source = host
    detail = ""
    if host == "www.mail-archive.com":
        dated = soup.select_one("span.date")
        value = dated.get_text(" ", strip=True) if dated else None
        detail = "message date"
    elif host == "mailman.haskell.org":
        dated = soup.select_one(".email-date span.date")
        value = dated.get_text(" ", strip=True) if dated else None
        detail = "message date"
    elif host == "pkg.go.dev":
        dated = soup.select_one('[data-test-id="UnitHeader-commitTime"]')
        value = dated.get_text(" ", strip=True) if dated else None
        status = "published"
        detail = "module version publication"
    date = normalize_date(value)
    if not date:
        return None
    return Resolution(
        url,
        status,
        date,
        source,
        "high",
        detail,
        payload.get("status"),
    )


def versioned_documentation_resolution(
    session: requests.Session, cache_dir: Path, url: str, timeout: float
) -> Resolution | None:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host == "zio.dev" and parsed.path.startswith("/1.0.18/"):
        return Resolution(
            url,
            "published",
            "2023-02-06",
            "github-tag",
            "high",
            "zio/zio tag v1.0.18 commit date",
        )
    if host == "ocaml.org":
        match = re.match(r"/p/([^/]+)/([^/]+)", parsed.path)
        if not match:
            return None
        package_url = f"https://ocaml.org/p/{match.group(1)}/{match.group(2)}"
        payload = fetch(session, cache_dir, package_url, timeout)
        if payload.get("status") != 200:
            return None
        soup = BeautifulSoup(response_body(payload), "html.parser")
        heading = soup.find(
            lambda tag: tag.name in {"h1", "h2", "h3"}
            and "Published:" in tag.get_text(" ", strip=True)
        )
        date = normalize_date(heading.get_text(" ", strip=True)) if heading else None
        if date:
            return Resolution(
                url,
                "published",
                date,
                "ocaml-package",
                "high",
                f"{match.group(1)} {match.group(2)} package publication",
                payload.get("status"),
            )
    return None


def citeseer_archive_resolution(
    session: requests.Session, cache_dir: Path, url: str, timeout: float
) -> Resolution | None:
    if urlparse(url).netloc.lower() != "citeseerx.ist.psu.edu":
        return None
    cache_url = f"HEAD-INSECURE {url}"
    payload = load_cached(cache_dir, cache_url)
    if payload is None:
        try:
            requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]
            response = session.head(
                url,
                timeout=timeout,
                allow_redirects=True,
                verify=False,
                headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
            )
            payload = {
                "requested_url": url,
                "final_url": response.url,
                "status": response.status_code,
                "headers": dict(response.headers),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
        except requests.RequestException as exc:
            payload = {
                "requested_url": url,
                "status": None,
                "error": f"{type(exc).__name__}: {exc}",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
        store_cached(cache_dir, cache_url, payload)
    final_url = payload.get("final_url", "")
    archived = url_encoded_date_resolution(final_url)
    if archived and archived.status == "archived":
        return Resolution(
            url,
            "archived",
            archived.date,
            "citeseer-wayback-redirect",
            "low",
            final_url,
            payload.get("status"),
        )
    return None


def url_encoded_date_resolution(url: str) -> Resolution | None:
    parsed = urlparse(url)
    if parsed.netloc.lower() == "web.archive.org":
        match = re.search(r"/web/(\d{4})(\d{2})(\d{2})", parsed.path)
        if match:
            date = normalize_date("-".join(match.groups()))
            if date:
                return Resolution(
                    url, "archived", date, "url", "medium", "Wayback timestamp"
                )
    match = re.search(
        r"(?<!\d)((?:18|19|20)\d{2})[-_/](1[0-2]|0?[1-9])"
        r"[-_/](3[01]|[12]\d|0?[1-9])(?!\d)",
        unquote(parsed.path),
    )
    if match:
        date = normalize_date("-".join(match.groups()))
        if date:
            return Resolution(
                url, "published", date, "url", "medium", "date encoded in URL"
            )
    return None


def hackage_resolution(
    session: requests.Session, cache_dir: Path, url: str, timeout: float
) -> Resolution | None:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    package: str | None = None
    exact_release = False
    match = HACKAGE_RE.search(url)
    if match:
        package = re.sub(
            r"\.(?:tar\.gz|cabal)$", "", match.group("package"), flags=re.I
        )
        exact_release = True
    elif host == "www.stackage.org":
        path = unquote(parsed.path).strip("/").split("/")
        if "package" in path:
            package = path[path.index("package") + 1].removesuffix(".html")
            exact_release = bool(
                path[0].startswith(("lts-", "nightly-"))
                and re.search(r"-\d", package)
            )
    elif host in {"flora.pm", "dev.flora.pm"}:
        match = re.search(r"/packages/@hackage/([^/?#]+)", unquote(parsed.path), re.I)
        if match:
            package = match.group(1)
    elif host in {"hackage.haskell.org", "hackage-content.haskell.org"}:
        match = re.search(r"/package/([^/?#]+)", parsed.path, re.I)
        if match:
            package = match.group(1).removesuffix(".html")
            exact_release = bool(re.search(r"-\d", package))
    if not package:
        return None

    if not exact_release:
        versions_url = f"https://hackage.haskell.org/package/{quote(package)}.json"
        versions_payload = fetch(session, cache_dir, versions_url, timeout)
        if versions_payload.get("status") != 200:
            return None
        try:
            versions = json.loads(response_body(versions_payload))
        except json.JSONDecodeError:
            return None
        if not isinstance(versions, dict) or not versions:
            return None
        package = f"{package}-{next(iter(versions))}"

    upload_url = (
        f"https://hackage.haskell.org/package/{quote(package, safe='+.-')}/upload-time"
    )
    payload = fetch(session, cache_dir, upload_url, timeout)
    if payload.get("status") != 200:
        return None
    date = normalize_date(response_body(payload).decode("utf-8", errors="replace"))
    if date:
        return Resolution(
            url,
            "uploaded",
            date,
            "hackage-upload-time",
            "high",
            f"release upload for {package}",
            payload.get("status"),
        )
    return None


def github_resolution(
    session: requests.Session, cache_dir: Path, url: str, timeout: float
) -> Resolution | None:
    api_url: str | None = None
    source = "github-api"
    if urlparse(url).netloc.lower() == "api.github.com":
        api_url = url
    else:
        match = GITHUB_REPO_RE.match(url)
        if match:
            api_url = (
                f"https://api.github.com/repos/{match.group('owner')}/"
                f"{match.group('repo')}"
            )
    if not api_url:
        return None
    payload = fetch(session, cache_dir, api_url, timeout)
    if payload.get("status") != 200:
        return None
    try:
        node = json.loads(response_body(payload))
    except json.JSONDecodeError:
        return None
    candidates: list[dict[str, Any]]
    if isinstance(node, list):
        candidates = [item for item in node if isinstance(item, dict)]
    elif isinstance(node, dict):
        candidates = [node]
    else:
        candidates = []
    dates = [
        normalize_date(item.get("created_at"))
        for item in candidates
        if item.get("created_at")
    ]
    dates = [date for date in dates if date]
    if dates:
        return Resolution(
            url,
            "created",
            min(dates),
            source,
            "high",
            "created_at",
            payload.get("status"),
        )
    return None


def source_specific_resolution(
    session: requests.Session, cache_dir: Path, url: str, timeout: float
) -> Resolution | None:
    static = url_encoded_date_resolution(url)
    if static:
        return static
    for resolver in (
        crossref_resolution,
        stackexchange_resolution,
        reddit_resolution,
        hackage_resolution,
        github_resolution,
        scholarly_title_resolution,
        community_page_resolution,
        versioned_documentation_resolution,
        citeseer_archive_resolution,
    ):
        result = resolver(session, cache_dir, url, timeout)
        if result:
            return result
    return None


def aggressive_header_resolution(
    session: requests.Session, cache_dir: Path, url: str, timeout: float
) -> Resolution | None:
    static = url_encoded_date_resolution(url)
    if static:
        return static
    payload = fetch_head(session, cache_dir, url, timeout)
    if payload.get("status") not in {200, 203, 204, 206}:
        return None
    headers = {key.lower(): value for key, value in payload.get("headers", {}).items()}
    date = normalize_date(headers.get("last-modified"))
    if date:
        return Resolution(
            url,
            "modified",
            date,
            "http-header",
            "low",
            "HTTP Last-Modified",
            payload.get("status"),
        )
    return None


def document_metadata_resolution(
    session: requests.Session, cache_dir: Path, url: str, timeout: float
) -> Resolution | None:
    if not re.search(r"\.(?:pdf|ps)(?:$|[?#])", urlparse(url).path, re.I):
        return None
    payload = fetch_range(session, cache_dir, url, timeout)
    if payload.get("status") not in {200, 206}:
        return None
    text = response_body(payload).decode("latin-1", errors="replace")
    patterns = (
        ("created", r"/CreationDate\s*\(D:(\d{4})(\d{2})(\d{2})"),
        ("created", r"<(?:xmp:)?CreateDate>([^<]+)</"),
        ("created", r"%%CreationDate:\s*([^\r\n]+)"),
        ("modified", r"/ModDate\s*\(D:(\d{4})(\d{2})(\d{2})"),
        ("modified", r"<(?:xmp:)?ModifyDate>([^<]+)</"),
    )
    for status, pattern in patterns:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        raw = "-".join(match.groups()) if len(match.groups()) == 3 else match.group(1)
        date = normalize_date(raw)
        if not date:
            continue
        try:
            if len(date) == 10 and datetime.fromisoformat(date).date() > datetime.now().date():
                continue
        except ValueError:
            continue
        return Resolution(
            url,
            status,
            date,
            "document-metadata",
            "low",
            pattern.split(r"\s", 1)[0].lstrip("/<"),
            payload.get("status"),
        )
    return None


def generic_resolution(
    session: requests.Session, cache_dir: Path, url: str, timeout: float
) -> Resolution | None:
    payload = fetch(session, cache_dir, url, timeout)
    status = payload.get("status")
    if status != 200:
        return Resolution(
            url,
            None,
            None,
            "unresolved",
            "none",
            payload.get("error", f"HTTP {status}"),
            status,
        )
    content_type = payload.get("headers", {}).get("Content-Type", "").lower()
    body = response_body(payload)
    if "html" in content_type or body.lstrip().startswith((b"<!DOCTYPE", b"<html")):
        requested = urlparse(url)
        final = urlparse(payload.get("final_url", url))
        document_path = re.search(
            r"\.(?:pdf|ps|gz|zip|tar)(?:$|[?#])", requested.path, re.I
        )
        allow_jsonld = (
            requested.netloc.lower() == final.netloc.lower() and not document_path
        )
        result = explicit_html_date(body, url, allow_jsonld=allow_jsonld)
        if result:
            return Resolution(
                result.url,
                result.status,
                result.date,
                result.source,
                result.confidence,
                result.detail,
                status,
            )
    return Resolution(url, None, None, "unresolved", "none", "no explicit date", status)


def resolve_one(
    cache_dir: Path,
    url: str,
    timeout: float,
    generic: bool,
    aggressive: bool,
    skip_source_specific: bool,
) -> Resolution:
    session = requests.Session()
    try:
        if not skip_source_specific:
            result = source_specific_resolution(session, cache_dir, url, timeout)
            if result:
                return result
        else:
            result = url_encoded_date_resolution(url)
            if result:
                return result
        is_document = bool(
            re.search(
                r"\.(?:pdf|ps|ps\.gz|gz|zip|tar|tar\.gz)(?:$|[?#])",
                urlparse(url).path,
                re.I,
            )
        )
        if is_document:
            result = document_metadata_resolution(session, cache_dir, url, timeout)
            if result:
                return result
        if generic and not is_document:
            result = generic_resolution(session, cache_dir, url, timeout)
            if result:
                if result.date or not aggressive:
                    return result
        if aggressive:
            result = aggressive_header_resolution(session, cache_dir, url, timeout)
            if result:
                return result
        return Resolution(url, None, None, "unresolved", "none", "no rule")
    finally:
        session.close()


def select_missing(
    lines: list[str], domains: set[str] | None, include_indexed: bool = False
) -> list[str]:
    selected: list[str] = []
    for line in lines:
        if not line.startswith(("http://", "https://")):
            continue
        parts = line.split("\t")
        eligible = {"N/A", "indexed"} if include_indexed else {"N/A"}
        if len(parts) < 2 or parts[1] not in eligible:
            continue
        url = parts[0]
        if domains and urlparse(url).netloc.lower() not in domains:
            continue
        selected.append(url)
    return selected


def title_key(url: str) -> tuple[str, ...] | None:
    parsed = urlparse(url)
    last = unquote(parsed.path).strip("/").split("/")[-1]
    last = re.sub(r"\.(?:html?|pdf|ps|gz|xml|bib|json)$", "", last, flags=re.I)
    last = re.sub(r"^\d+[_-]", "", last)
    ignored = {"fulltext", "download", "view", "index", "article", "publication", "paper"}
    tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", last.lower())
        if token not in ignored
    ]
    if len(tokens) < 5 or sum(map(len, tokens)) < 25:
        return None
    return ("research-title", *tokens)


def equivalent_keys(url: str) -> list[tuple[str, ...]]:
    keys: list[tuple[str, ...]] = []
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    canonical_host = host[4:] if host.startswith("www.") else host
    canonical_path = unquote(parsed.path).rstrip("/") or "/"
    keys.append(("canonical-url", canonical_host, canonical_path))

    stack_match = STACKEXCHANGE_RE.search(url)
    if stack_match:
        keys.append(("stack-question", stack_match.group("id")))
    query = parse_qs(parsed.query)
    if "stackprinter" in parsed.netloc.lower() and query.get("question"):
        keys.append(("stack-question", query["question"][0]))

    path = parsed.path.strip("/").split("/")
    if (
        parsed.netloc.lower() == "api.github.com"
        and len(path) >= 5
        and path[0] == "repos"
        and path[3] == "contents"
    ):
        keys.append(
            (
                "github-file",
                path[1].lower(),
                path[2].lower(),
                unquote("/".join(path[4:])),
            )
        )
    elif (
        parsed.netloc.lower() == "github.com"
        and len(path) >= 5
        and path[2] in {"blob", "raw"}
    ):
        keys.append(
            (
                "github-file",
                path[0].lower(),
                path[1].lower(),
                unquote("/".join(path[4:])),
            )
        )
    elif parsed.netloc.lower() == "raw.githubusercontent.com" and len(path) >= 4:
        keys.append(
            (
                "github-file",
                path[0].lower(),
                path[1].lower(),
                unquote("/".join(path[3:])),
            )
        )
    research_title = title_key(url)
    if research_title:
        keys.append(research_title)
    return keys


def equivalent_resolutions(lines: list[str], urls: list[str]) -> list[Resolution]:
    candidates: dict[tuple[str, ...], list[tuple[str, str, str]]] = {}
    for line in lines:
        if not line.startswith(("http://", "https://")):
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        if parts[1] in {"N/A", "indexed"}:
            continue
        for key in equivalent_keys(parts[0]):
            candidates.setdefault(key, []).append((parts[1], parts[2], parts[0]))

    known: dict[tuple[str, ...], tuple[str, str, str]] = {}
    for key, values in candidates.items():
        if len({(status, date) for status, date, _ in values}) == 1:
            known[key] = values[0]

    results: list[Resolution] = []
    for url in urls:
        host = urlparse(url).netloc.lower()
        allowed_keys = [
            key
            for key in equivalent_keys(url)
            if key[0] != "research-title" or "researchgate.net" in host
        ]
        match = next((known[key] for key in allowed_keys if key in known), None)
        if not match:
            continue
        status, date, evidence_url = match
        results.append(
            Resolution(
                url,
                status,
                date,
                "equivalent-link",
                "high",
                f"same item as {evidence_url}",
            )
        )
    return results


def pullpush_resolutions(
    cache_dir: Path, urls: list[str], timeout: float
) -> list[Resolution]:
    by_id: dict[str, list[str]] = {}
    for url in urls:
        match = REDDIT_RE.search(url)
        if match:
            by_id.setdefault(match.group("id").lower(), []).append(url)
    if not by_id:
        return []

    found: dict[str, Any] = {}
    session = requests.Session()
    try:
        ids = list(by_id)
        for start in range(0, len(ids), 100):
            batch = ids[start : start + 100]
            api_url = (
                "https://api.pullpush.io/reddit/search/submission/"
                f"?ids={quote(','.join(batch), safe=',')}&size=100"
            )
            payload = fetch(session, cache_dir, api_url, timeout)
            if payload.get("status") != 200:
                continue
            try:
                items = json.loads(response_body(payload)).get("data", [])
            except json.JSONDecodeError:
                continue
            for item in items:
                item_id = str(item.get("id", "")).lower()
                if item_id in by_id and item.get("created_utc"):
                    found[item_id] = item.get("created_utc")
    finally:
        session.close()

    results: list[Resolution] = []
    for item_id, timestamp in found.items():
        date = normalize_date(timestamp)
        if not date:
            continue
        for url in by_id[item_id]:
            results.append(
                Resolution(
                    url,
                    "created",
                    date,
                    "pullpush-reddit-archive",
                    "medium",
                    f"submission {item_id} created_utc",
                )
            )
    return results


def arctic_shift_resolutions(
    cache_dir: Path, urls: list[str], timeout: float
) -> list[Resolution]:
    by_id: dict[str, list[str]] = {}
    for url in urls:
        match = REDDIT_RE.search(url)
        if match:
            by_id.setdefault(match.group("id").lower(), []).append(url)
    if not by_id:
        return []

    found: dict[str, Any] = {}
    session = requests.Session()
    try:
        ids = list(by_id)
        for start in range(0, len(ids), 500):
            batch = ids[start : start + 500]
            api_url = (
                "https://arctic-shift.photon-reddit.com/api/posts/ids"
                f"?ids={quote(','.join(batch), safe=',')}&fields=id,created_utc"
            )
            payload = fetch(session, cache_dir, api_url, timeout)
            if payload.get("status") != 200:
                continue
            try:
                items = json.loads(response_body(payload)).get("data", [])
            except json.JSONDecodeError:
                continue
            for item in items:
                item_id = str(item.get("id", "")).lower()
                if item_id in by_id and item.get("created_utc"):
                    found[item_id] = item["created_utc"]
    finally:
        session.close()

    results: list[Resolution] = []
    for item_id, timestamp in found.items():
        date = normalize_date(timestamp)
        if not date:
            continue
        for url in by_id[item_id]:
            results.append(
                Resolution(
                    url,
                    "created",
                    date,
                    "arctic-shift-reddit-archive",
                    "medium",
                    f"submission {item_id} created_utc",
                )
            )
    return results


def apply_resolutions(
    path: Path, lines: list[str], resolutions: dict[str, Resolution]
) -> int:
    changed = 0
    output: list[str] = []
    for line in lines:
        parts = line.split("\t")
        if (
            line.startswith(("http://", "https://"))
            and len(parts) >= 2
            and parts[1] in {"N/A", "indexed"}
        ):
            result = resolutions.get(parts[0])
            if result and result.status and result.date:
                line = f"{parts[0]}\t{result.status}\t{result.date}"
                changed += 1
        output.append(line)
    if changed:
        path.write_text("\n".join(output) + "\n", encoding="utf-8", newline="\n")
    return changed


def write_report(path: Path, resolutions: list[Resolution]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for result in resolutions:
            handle.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, default=Path("io_links.md"))
    parser.add_argument(
        "--cache-dir", type=Path, default=Path("scratch/io-link-date-cache")
    )
    parser.add_argument(
        "--pullpush-reddit",
        action="store_true",
        help="Resolve Reddit submission dates in batches via the PullPush archive",
    )
    parser.add_argument(
        "--arctic-shift-reddit",
        action="store_true",
        help="Resolve Reddit submission dates in batches via Arctic Shift",
    )
    parser.add_argument(
        "--index-unresolved",
        action="store_true",
        help="Fill any selected unresolved rows as indexed on today's date",
    )
    parser.add_argument(
        "--include-indexed",
        action="store_true",
        help="Re-audit rows previously assigned a fallback indexed date",
    )
    parser.add_argument(
        "--aggressive",
        action="store_true",
        help="Allow URL dates and HTTP Last-Modified with explicit provenance labels",
    )
    parser.add_argument(
        "--skip-source-specific",
        action="store_true",
        help="Skip specialized API/page resolvers; useful for broad HEAD-only passes",
    )
    parser.add_argument(
        "--documents-only",
        action="store_true",
        help="Only select missing PDF and PostScript URLs",
    )
    parser.add_argument(
        "--report", type=Path, default=Path("scratch/io-link-date-report.jsonl")
    )
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--offset", type=int, default=0, help="Skip this many selected missing rows"
    )
    parser.add_argument(
        "--domain", action="append", help="Only resolve this hostname (repeatable)"
    )
    parser.add_argument(
        "--generic",
        action="store_true",
        help="Fetch generic HTML pages after source-specific rules",
    )
    parser.add_argument(
        "--apply", action="store_true", help="Rewrite resolved N/A rows in place"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    path = args.file.resolve()
    lines = path.read_text(encoding="utf-8").splitlines()
    domains = {item.lower() for item in args.domain} if args.domain else None
    urls = select_missing(lines, domains, args.include_indexed)
    if args.documents_only:
        urls = [
            url
            for url in urls
            if re.search(r"\.(?:pdf|ps)(?:$|[?#])", urlparse(url).path, re.I)
        ]
    if args.offset:
        urls = urls[args.offset :]
    if args.limit is not None:
        urls = urls[: args.limit]
    print(f"Resolving {len(urls)} missing rows", flush=True)

    started = time.monotonic()
    results = equivalent_resolutions(lines, urls)
    if args.pullpush_reddit:
        existing = {item.url for item in results}
        results.extend(
            item
            for item in pullpush_resolutions(
                args.cache_dir.resolve(), urls, args.timeout
            )
            if item.url not in existing
        )
    if args.arctic_shift_reddit:
        existing = {item.url for item in results if item.date}
        results.extend(
            item
            for item in arctic_shift_resolutions(
                args.cache_dir.resolve(), urls, args.timeout
            )
            if item.url not in existing
        )
    if args.index_unresolved:
        existing = {item.url for item in results}
        indexed_date = datetime.now().date().isoformat()
        results.extend(
            Resolution(
                url,
                "indexed",
                indexed_date,
                "fallback-index",
                "low",
                "no authored/publication date recovered",
            )
            for url in urls
            if url not in existing
        )
    propagated_urls = {item.url for item in results}
    network_urls = [url for url in urls if url not in propagated_urls]
    if results:
        print(f"{len(results)} resolved from equivalent links", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                resolve_one,
                args.cache_dir.resolve(),
                url,
                args.timeout,
                args.generic,
                args.aggressive,
                args.skip_source_specific,
            ): url
            for url in network_urls
        }
        for completed, future in enumerate(
            concurrent.futures.as_completed(futures), start=1
        ):
            url = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:  # Keep one bad host from losing the batch.
                results.append(
                    Resolution(
                        url,
                        None,
                        None,
                        "error",
                        "none",
                        f"{type(exc).__name__}: {exc}",
                    )
                )
            if completed % 100 == 0 or completed == len(futures):
                resolved = sum(bool(item.date) for item in results)
                elapsed = time.monotonic() - started
                print(
                    f"{completed}/{len(futures)} checked; "
                    f"{resolved} resolved; {elapsed:.1f}s",
                    flush=True,
                )

    order = {url: index for index, url in enumerate(urls)}
    results.sort(key=lambda item: order[item.url])
    write_report(args.report.resolve(), results)
    resolved_by_url = {item.url: item for item in results}
    resolved = sum(bool(item.date) for item in results)
    print(f"Resolved {resolved}/{len(results)}")
    if args.apply:
        changed = apply_resolutions(path, lines, resolved_by_url)
        print(f"Updated {changed} rows in {path}")
    else:
        print("Dry run only; pass --apply to edit the Markdown file")
    return 0


if __name__ == "__main__":
    sys.exit(main())

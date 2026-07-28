#!/usr/bin/env python3
"""Audit indexed ResearchGate and DBLP links without modifying io_links.md.

ResearchGate publication slugs are matched conservatively against Crossref,
then OpenAlex. DBLP author and index pages are classified by page semantics;
conference-edition pages with an explicit year in their stable DBLP key are
resolved from that key. Results are checkpointed so API work is resumable.
"""

from __future__ import annotations

import argparse
import difflib
import html
import json
import re
import time
import unicodedata
from datetime import date
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests


USER_AGENT = (
    "io-links-date-audit/2.0 "
    "(scholarly metadata maintenance; "
    "https://github.com/alexyorke/alexyorke.github.io)"
)
TARGET_HOSTS = {"researchgate.net", "www.researchgate.net", "dblp.org"}


def clean_title(value: str) -> str:
    value = html.unescape(re.sub(r"<[^>]+>", " ", value))
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.findall(r"[a-z0-9]+", value))


def title_similarity(left: str, right: str) -> float:
    a = clean_title(left)
    b = clean_title(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    sequence = difflib.SequenceMatcher(None, a, b).ratio()
    a_tokens = a.split()
    b_tokens = b.split()
    a_set = set(a_tokens)
    b_set = set(b_tokens)
    precision = len(a_set & b_set) / len(b_set)
    recall = len(a_set & b_set) / len(a_set)
    token_f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    return max(sequence, token_f1)


def publication_title(url: str) -> str | None:
    match = re.search(
        r"/publication/\d+_([^?#]+)", unquote(urlparse(url).path), flags=re.I
    )
    if not match:
        return None
    return re.sub(r"[_-]+", " ", match.group(1)).strip()


def format_date_parts(parts: object) -> str | None:
    if not isinstance(parts, list) or not parts or not isinstance(parts[0], list):
        return None
    values = parts[0]
    if not values or not isinstance(values[0], int):
        return None
    year = values[0]
    if not 1000 <= year <= date.today().year:
        return None
    if len(values) == 1:
        return f"{year:04d}"
    month = values[1]
    if not isinstance(month, int) or not 1 <= month <= 12:
        return f"{year:04d}"
    if len(values) == 2:
        return f"{year:04d}-{month:02d}"
    day = values[2]
    if not isinstance(day, int):
        return f"{year:04d}-{month:02d}"
    try:
        parsed = date(year, month, day)
    except ValueError:
        return f"{year:04d}-{month:02d}"
    return parsed.isoformat()


def crossref_date(item: dict) -> tuple[str | None, str | None]:
    # The first public manifestation is the best fit for the requested
    # publication date. Fall back to Crossref's generic publication fields.
    candidates: list[tuple[str, str]] = []
    for field in ("published-online", "published-print"):
        value = format_date_parts((item.get(field) or {}).get("date-parts"))
        if value:
            candidates.append((value, field))
    if candidates:
        return min(candidates, key=lambda pair: pair[0])
    for field in ("published", "issued"):
        value = format_date_parts((item.get(field) or {}).get("date-parts"))
        if value:
            return value, field
    return None, None


def select_match(query_title: str, candidates: list[dict]) -> tuple[dict | None, dict]:
    ranked: list[dict] = []
    for candidate in candidates:
        raw_title = candidate.get("title")
        if isinstance(raw_title, list):
            raw_title = raw_title[0] if raw_title else ""
        if not raw_title:
            raw_title = candidate.get("display_name") or ""
        similarity = title_similarity(query_title, str(raw_title))
        ranked.append(
            {
                "candidate": candidate,
                "title": str(raw_title),
                "similarity": round(similarity, 4),
            }
        )
    ranked.sort(key=lambda item: item["similarity"], reverse=True)
    best = ranked[0] if ranked else None
    runner_up = ranked[1] if len(ranked) > 1 else None
    diagnostics = {
        "best_title": best["title"] if best else None,
        "best_similarity": best["similarity"] if best else None,
        "runner_up_title": runner_up["title"] if runner_up else None,
        "runner_up_similarity": runner_up["similarity"] if runner_up else None,
    }
    if not best:
        return None, diagnostics
    exact = clean_title(query_title) == clean_title(best["title"])
    margin = (
        best["similarity"] - runner_up["similarity"]
        if runner_up
        else best["similarity"]
    )
    if exact or (best["similarity"] >= 0.96 and margin >= 0.08):
        return best["candidate"], diagnostics
    return None, diagnostics


def unresolved(
    url: str, reason: str, *, evidence: object = None, source: str = "audit"
) -> dict:
    return {
        "url": url,
        "status": None,
        "date": None,
        "evidence": evidence,
        "source": source,
        "unresolved_reason": reason,
    }


def crossref_lookup(
    session: requests.Session, title: str, timeout: float
) -> tuple[list[dict], str | None]:
    response = None
    for attempt in range(4):
        try:
            response = session.get(
                "https://api.crossref.org/works",
                params={
                    "query.title": title,
                    "rows": 5,
                    "select": (
                        "DOI,title,published,published-print,published-online,"
                        "issued,type,score,URL"
                    ),
                },
                timeout=timeout,
            )
        except requests.RequestException as exc:
            return [], f"{type(exc).__name__}: {exc}"
        if response.status_code != 429:
            break
        time.sleep(2 * (attempt + 1))
    assert response is not None
    if response.status_code != 200:
        return [], f"HTTP {response.status_code}"
    try:
        items = response.json()["message"]["items"]
    except (KeyError, TypeError, ValueError):
        return [], "invalid JSON response"
    return [item for item in items if isinstance(item, dict)], None


def openalex_lookup(
    session: requests.Session, title: str, timeout: float
) -> tuple[list[dict], str | None]:
    try:
        response = session.get(
            "https://api.openalex.org/works",
            params={
                "search": title,
                "per-page": 5,
                "select": (
                    "id,doi,display_name,publication_date,publication_year,type"
                ),
            },
            timeout=timeout,
        )
    except requests.RequestException as exc:
        return [], f"{type(exc).__name__}: {exc}"
    if response.status_code != 200:
        return [], f"HTTP {response.status_code}"
    try:
        items = response.json()["results"]
    except (KeyError, TypeError, ValueError):
        return [], "invalid JSON response"
    return [item for item in items if isinstance(item, dict)], None


def semantic_scholar_lookup(
    session: requests.Session, title: str, timeout: float
) -> tuple[list[dict], str | None]:
    try:
        response = session.get(
            "https://api.semanticscholar.org/graph/v1/paper/search/match",
            params={
                "query": title,
                "fields": (
                    "title,year,publicationDate,externalIds,venue,paperId"
                ),
            },
            timeout=timeout,
        )
    except requests.RequestException as exc:
        return [], f"{type(exc).__name__}: {exc}"
    if response.status_code != 200:
        return [], f"HTTP {response.status_code}"
    try:
        data = response.json().get("data")
    except (AttributeError, TypeError, ValueError):
        return [], "invalid JSON response"
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return [], None
    return [item for item in data if isinstance(item, dict)], None


def crossref_result(url: str, title: str, candidate: dict, match: dict) -> dict:
    value, field = crossref_date(candidate)
    evidence = {
        "query_title": title,
        **match,
        "matched_title": (candidate.get("title") or [None])[0],
        "doi": candidate.get("DOI"),
        "work_type": candidate.get("type"),
        "date_field": field,
        "published_online": (candidate.get("published-online") or {}).get(
            "date-parts"
        ),
        "published_print": (candidate.get("published-print") or {}).get(
            "date-parts"
        ),
        "published": (candidate.get("published") or {}).get("date-parts"),
    }
    if not value:
        return unresolved(
            url,
            "A high-confidence Crossref title match had no usable publication date.",
            evidence=evidence,
            source="Crossref title search",
        )
    return {
        "url": url,
        "status": "publication",
        "date": value,
        "evidence": evidence,
        "source": "Crossref title search",
        "unresolved_reason": None,
    }


def openalex_result(url: str, title: str, candidate: dict, match: dict) -> dict:
    value = candidate.get("publication_date")
    if not re.fullmatch(r"\d{4}(?:-\d{2}){0,2}", str(value or "")):
        year = candidate.get("publication_year")
        value = str(year) if isinstance(year, int) else None
    evidence = {
        "query_title": title,
        **match,
        "matched_title": candidate.get("display_name"),
        "openalex_id": candidate.get("id"),
        "doi": candidate.get("doi"),
        "work_type": candidate.get("type"),
        "publication_date": candidate.get("publication_date"),
    }
    if not value:
        return unresolved(
            url,
            "A high-confidence OpenAlex title match had no usable publication date.",
            evidence=evidence,
            source="OpenAlex works search",
        )
    return {
        "url": url,
        "status": "publication",
        "date": value,
        "evidence": evidence,
        "source": "OpenAlex works search",
        "unresolved_reason": None,
    }


def semantic_scholar_result(
    url: str, title: str, candidate: dict, match: dict
) -> dict:
    value = candidate.get("publicationDate")
    if not re.fullmatch(r"\d{4}(?:-\d{2}){0,2}", str(value or "")):
        year = candidate.get("year")
        value = str(year) if isinstance(year, int) else None
    evidence = {
        "query_title": title,
        **match,
        "matched_title": candidate.get("title"),
        "semantic_scholar_paper_id": candidate.get("paperId"),
        "external_ids": candidate.get("externalIds"),
        "venue": candidate.get("venue"),
        "publication_date": candidate.get("publicationDate"),
        "publication_year": candidate.get("year"),
    }
    if not value:
        return unresolved(
            url,
            (
                "A high-confidence Semantic Scholar title match had no usable "
                "publication date."
            ),
            evidence=evidence,
            source="Semantic Scholar title-match API",
        )
    return {
        "url": url,
        "status": "publication",
        "date": value,
        "evidence": evidence,
        "source": "Semantic Scholar title-match API",
        "unresolved_reason": None,
    }


def classify_dblp(url: str) -> dict:
    path = urlparse(url).path
    if path.startswith("/pid/"):
        canonical = re.sub(r"\.html$", "", path)
        return unresolved(
            url,
            (
                "This is a mutable DBLP author profile, not a publication. "
                "DBLP exposes modification metadata but no defensible profile "
                "creation or publication date."
            ),
            evidence={"page_type": "author profile", "canonical_path": canonical},
            source="DBLP URL semantics",
        )
    if path.rstrip("/") == "/db/conf/haskell/index":
        return unresolved(
            url,
            (
                "This is a continuously updated conference-series index rather "
                "than a single publication; it has no single creation or "
                "publication date."
            ),
            evidence={"page_type": "conference series index"},
            source="DBLP URL semantics",
        )
    # Stable conference-edition DBLP keys encode the event year. Resolve only
    # these explicit cases; do not infer years from opaque journal volume keys.
    match = re.fullmatch(r"/db/conf/([^/]+)/[^/]*?(\d{2})(?:\.html)?", path)
    if match:
        short_year = int(match.group(2))
        year = 1900 + short_year if short_year >= 50 else 2000 + short_year
        return {
            "url": url,
            "status": "publication",
            "date": str(year),
            "evidence": {
                "page_type": "conference edition bibliography",
                "stable_dblp_key": path.removesuffix(".html"),
                "encoded_event_year": match.group(2),
            },
            "source": "DBLP stable conference-edition key",
            "unresolved_reason": None,
        }
    return unresolved(
        url,
        (
            "The DBLP page is a bibliography/index page with an opaque volume "
            "key. The DBLP endpoint throttled repeated metadata requests, and "
            "the URL alone does not establish a publication date."
        ),
        evidence={"page_type": "bibliography or volume index", "path": path},
        source="DBLP URL semantics",
    )


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, default=Path("io_links.md"))
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("scratch/researchgate-dblp-continuation-audit.json"),
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=Path("scratch/researchgate-dblp-continuation-cache.json"),
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--delay", type=float, default=0.25)
    parser.add_argument(
        "--skip-crossref",
        action="store_true",
        help="Do not make new Crossref requests; use any cached responses only.",
    )
    parser.add_argument(
        "--openalex",
        action="store_true",
        help="Use OpenAlex for unresolved ResearchGate publications.",
    )
    parser.add_argument(
        "--semantic-scholar",
        action="store_true",
        help="Use Semantic Scholar for unresolved ResearchGate publications.",
    )
    args = parser.parse_args()

    targets: list[str] = []
    for line in args.file.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) != 3 or parts[1] != "indexed":
            continue
        url = parts[0]
        if urlparse(url).netloc.casefold() in TARGET_HOSTS:
            targets.append(url)
    targets = list(dict.fromkeys(targets))

    cache: dict[str, dict] = {}
    if args.cache.exists():
        cache = json.loads(args.cache.read_text(encoding="utf-8"))
        cache = {
            key: value
            for key, value in cache.items()
            if value.get("error") not in {"HTTP 429", "HTTP 502", "HTTP 503", "HTTP 504"}
        }

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    results: dict[str, dict] = {}
    researchgate = [url for url in targets if "researchgate.net" in urlparse(url).netloc]
    dblp = [url for url in targets if urlparse(url).netloc == "dblp.org"]

    consecutive_failures = 0
    stopped_service: str | None = None
    for index, url in enumerate(researchgate, 1):
        title = publication_title(url)
        if not title:
            page_type = urlparse(url).path.split("/")[1] or "root"
            results[url] = unresolved(
                url,
                (
                    "This ResearchGate URL is a mutable "
                    f"{page_type} page, not a dated publication item, and "
                    "ResearchGate does not expose a defensible creation date."
                ),
                evidence={"page_type": page_type},
                source="ResearchGate URL semantics",
            )
            continue

        cache_key = f"crossref:{url}"
        cached = cache.get(cache_key)
        if cached is None and args.skip_crossref:
            cached = {"items": [], "error": "Crossref skipped for this batch"}
        elif cached is None and stopped_service is None:
            items, error = crossref_lookup(session, title, args.timeout)
            cached = {"items": items, "error": error}
            cache[cache_key] = cached
            write_json(args.cache, cache)
            if error:
                consecutive_failures += 1
                if consecutive_failures >= 2:
                    stopped_service = "Crossref"
            else:
                consecutive_failures = 0
            time.sleep(args.delay)
        elif cached is None:
            cached = {"items": [], "error": f"{stopped_service} batch stopped"}

        candidate, match = select_match(title, cached.get("items") or [])
        if candidate:
            results[url] = crossref_result(url, title, candidate, match)
        else:
            results[url] = unresolved(
                url,
                (
                    "No sufficiently close and unambiguous Crossref title "
                    "match was found."
                ),
                evidence={"query_title": title, **match, "api_error": cached.get("error")},
                source="Crossref title search",
            )
        if index % 25 == 0:
            resolved = sum(bool(item.get("date")) for item in results.values())
            print(
                f"Crossref: {index}/{len(researchgate)} ResearchGate URLs; "
                f"{resolved} resolved",
                flush=True,
            )

    if args.openalex:
        consecutive_failures = 0
        stopped_service = None
        pending = [
            url
            for url in researchgate
            if not results[url].get("date") and publication_title(url)
        ]
        for index, url in enumerate(pending, 1):
            title = publication_title(url) or ""
            cache_key = f"openalex:{url}"
            cached = cache.get(cache_key)
            if cached is None and stopped_service is None:
                items, error = openalex_lookup(session, title, args.timeout)
                cached = {"items": items, "error": error}
                cache[cache_key] = cached
                write_json(args.cache, cache)
                if error:
                    consecutive_failures += 1
                    if consecutive_failures >= 2:
                        stopped_service = "OpenAlex"
                else:
                    consecutive_failures = 0
                time.sleep(args.delay)
            elif cached is None:
                cached = {"items": [], "error": f"{stopped_service} batch stopped"}

            candidate, match = select_match(title, cached.get("items") or [])
            if candidate:
                results[url] = openalex_result(url, title, candidate, match)
            else:
                prior = results[url]
                prior["evidence"] = {
                    "crossref": prior.get("evidence"),
                    "openalex": {
                        "query_title": title,
                        **match,
                        "api_error": cached.get("error"),
                    },
                }
                prior["source"] = "Crossref and OpenAlex title search"
                prior["unresolved_reason"] = (
                    "Neither Crossref nor OpenAlex returned a sufficiently "
                    "close and unambiguous title match."
                )
            if index % 25 == 0:
                resolved = sum(bool(item.get("date")) for item in results.values())
                print(
                    f"OpenAlex: {index}/{len(pending)} pending URLs; "
                    f"{resolved} total resolved",
                    flush=True,
                )

    if args.semantic_scholar:
        consecutive_failures = 0
        stopped_service = None
        pending = [
            url
            for url in researchgate
            if not results[url].get("date") and publication_title(url)
        ]
        for index, url in enumerate(pending, 1):
            title = publication_title(url) or ""
            cache_key = f"semantic-scholar:{url}"
            cached = cache.get(cache_key)
            if cached is None and stopped_service is None:
                items, error = semantic_scholar_lookup(
                    session, title, args.timeout
                )
                cached = {"items": items, "error": error}
                cache[cache_key] = cached
                write_json(args.cache, cache)
                if error:
                    consecutive_failures += 1
                    if consecutive_failures >= 2:
                        stopped_service = "Semantic Scholar"
                else:
                    consecutive_failures = 0
                time.sleep(args.delay)
            elif cached is None:
                cached = {
                    "items": [],
                    "error": f"{stopped_service} batch stopped",
                }

            candidate, match = select_match(title, cached.get("items") or [])
            if candidate:
                results[url] = semantic_scholar_result(
                    url, title, candidate, match
                )
            else:
                prior = results[url]
                prior["evidence"] = {
                    "prior_services": prior.get("evidence"),
                    "semantic_scholar": {
                        "query_title": title,
                        **match,
                        "api_error": cached.get("error"),
                    },
                }
                prior["source"] = (
                    f"{prior.get('source')}; Semantic Scholar title-match API"
                )
                prior["unresolved_reason"] = (
                    "No queried scholarly metadata service returned a "
                    "sufficiently close and unambiguous title match."
                )
            if index % 25 == 0:
                resolved = sum(bool(item.get("date")) for item in results.values())
                print(
                    f"Semantic Scholar: {index}/{len(pending)} pending URLs; "
                    f"{resolved} total resolved",
                    flush=True,
                )

    for url in dblp:
        results[url] = classify_dblp(url)

    ordered = [results[url] for url in targets]
    write_json(args.report, ordered)
    resolved = sum(bool(item.get("date")) for item in ordered)
    print(
        f"Wrote {len(ordered)} results ({resolved} resolved, "
        f"{len(ordered) - resolved} unresolved) to {args.report}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Resolve indexed ResearchGate paper dates through high-confidence DBLP title matches."""

from __future__ import annotations

import argparse
import difflib
import json
import re
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests


USER_AGENT = (
    "io-links-date-audit/1.0 "
    "(scholarly metadata maintenance; https://github.com/alexyorke/alexyorke.github.io)"
)


def title_from_url(url: str) -> str | None:
    match = re.search(r"/publication/\d+_(.+)", unquote(urlparse(url).path), re.I)
    if not match:
        return None
    return re.sub(r"[_-]+", " ", match.group(1)).strip()


def normalized_title(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def similarity(left: str, right: str) -> float:
    a = normalized_title(left)
    b = normalized_title(right)
    sequence = difflib.SequenceMatcher(None, a, b).ratio()
    a_tokens = set(a.split())
    b_tokens = set(b.split())
    union = a_tokens | b_tokens
    jaccard = len(a_tokens & b_tokens) / len(union) if union else 0.0
    return max(sequence, jaccard)


def query(
    session: requests.Session, title: str, timeout: float
) -> tuple[list[dict], str | None]:
    for attempt in range(6):
        try:
            response = session.get(
                "https://dblp.org/search/publ/api",
                params={"q": title, "format": "json", "h": 3},
                headers={"User-Agent": USER_AGENT},
                timeout=timeout,
            )
        except requests.RequestException as exc:
            if attempt == 5:
                return [], f"{type(exc).__name__}: {exc}"
            time.sleep(3 + attempt * 2)
            continue
        if response.status_code == 200:
            try:
                hits = response.json()["result"]["hits"].get("hit", [])
            except (KeyError, TypeError, ValueError):
                return [], "invalid DBLP response"
            if isinstance(hits, dict):
                hits = [hits]
            return [item for item in hits if isinstance(item, dict)], None
        if response.status_code == 429:
            time.sleep(10 + attempt * 5)
            continue
        return [], f"HTTP {response.status_code}"
    return [], "retry limit"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, default=Path("io_links.md"))
    parser.add_argument(
        "--report", type=Path, default=Path("scratch/researchgate-dblp-audit.json")
    )
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--delay", type=float, default=1.25)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    lines = args.file.read_text(encoding="utf-8").splitlines()
    urls = []
    for line in lines:
        parts = line.split("\t")
        if (
            len(parts) == 3
            and parts[1] == "indexed"
            and "researchgate.net" in urlparse(parts[0]).netloc.lower()
            and title_from_url(parts[0])
        ):
            urls.append(parts[0])

    previous = {}
    if args.report.exists():
        previous = {
            item["url"]: item
            for item in json.loads(args.report.read_text(encoding="utf-8"))
        }
    results = dict(previous)
    session = requests.Session()
    pending = [url for url in urls if url not in results]
    for count, url in enumerate(pending, 1):
        title = title_from_url(url) or ""
        hits, error = query(session, title, args.timeout)
        candidates = []
        for hit in hits:
            info = hit.get("info") or {}
            match_title = info.get("title") or ""
            score = similarity(title, match_title)
            candidates.append(
                {
                    "title": match_title,
                    "year": info.get("year"),
                    "doi": info.get("doi"),
                    "key": info.get("key"),
                    "similarity": round(score, 4),
                }
            )
        best = max(candidates, key=lambda item: item["similarity"], default=None)
        accepted = bool(
            best
            and best.get("year")
            and (
                best["similarity"] >= 0.92
                or normalized_title(title) == normalized_title(best["title"])
            )
        )
        results[url] = {
            "url": url,
            "query_title": title,
            "status": "publication" if accepted else None,
            "date": str(best["year"]) if accepted else None,
            "source": "dblp-title-search" if accepted else "unresolved",
            "evidence": best,
            "error": error,
        }
        if count % 20 == 0 or count == len(pending):
            resolved = sum(bool(item.get("date")) for item in results.values())
            print(f"{count}/{len(pending)} queried; {resolved} resolved", flush=True)
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(
                json.dumps(
                    sorted(results.values(), key=lambda item: item["url"]), indent=2
                )
                + "\n",
                encoding="utf-8",
                newline="\n",
            )
        time.sleep(args.delay)

    if args.apply:
        resolved = {
            url: item for url, item in results.items() if item.get("date")
        }
        changed = 0
        for index, line in enumerate(lines):
            parts = line.split("\t")
            if len(parts) != 3 or parts[1] != "indexed":
                continue
            item = resolved.get(parts[0])
            if not item:
                continue
            lines[index] = f"{parts[0]}\t{item['status']}\t{item['date']}"
            changed += 1
        args.file.write_text(
            "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
        )
        print(f"Updated {changed} rows", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

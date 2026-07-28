#!/usr/bin/env python3
"""Build the bounded continuation audit for selected documentation hosts.

This script intentionally applies only evidence collected before the audit was
stopped. It does not perform network requests and does not modify io_links.md.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "io_links.md"
OUTPUT = ROOT / "scratch" / "versioned-docs-continuation-audit.json"
HOSTS = {
    "book.realworldhaskell.org",
    "hackage.haskell.org",
    "lean-lang.org",
    "www.haskell.org",
    "www.unison-lang.org",
    "zio.dev",
}

LEAN_THESIS = "https://lean-lang.org/papers/thesis-sebastian.pdf"
HASKELL_GHC_BLOG = "https://www.haskell.org/ghc/blog/20210709-capi-usage.html"
HASKELL_PIPERMAIL_PDF = (
    "https://www.haskell.org/pipermail/beginners/attachments/"
    "20090424/UnderstandingHaskellMonads.pdf"
)


def unresolved_reason(url: str, host: str) -> str:
    path = urlsplit(url).path
    if host == "zio.dev":
        return (
            "Unversioned moving documentation/resource page; no stable "
            "publication or source-creation date was captured before the "
            "bounded audit stopped."
        )
    if host == "www.unison-lang.org":
        return (
            "Unversioned moving documentation/site page; no stable "
            "publication or source-creation date was captured."
        )
    if host == "lean-lang.org":
        if "/latest/" in path:
            return (
                "Moving latest-version documentation; a current release date "
                "would not date this specific changing page."
            )
        if "/4.19.0-rc2/" in path:
            return (
                "Version is explicit, but exact official 4.19.0-rc2 release "
                "evidence was not captured; the final 4.19.0 date is not a "
                "valid substitute."
            )
        return (
            "Unversioned moving online documentation/book page without "
            "captured edition or page-creation metadata."
        )
    if host == "hackage.haskell.org":
        if "/packages/tag/" in path:
            return "Dynamic package-tag catalog page with no stable publication date."
        if path.rstrip("/") in {
            "/package",
            "/packages",
            "/packages/candidates",
            "/packages/browse",
            "/api",
        }:
            return "Dynamic Hackage catalog/API page with no stable publication date."
        if "/packages/archive/" in path or "/package/" in path:
            return (
                "Package/release upload metadata was not captured for this "
                "exact target; unversioned package documentation may also "
                "move to a newer release."
            )
        return "No stable Hackage item date was captured."
    if host == "www.haskell.org":
        if "/haskellwiki/" in path:
            return (
                "Wiki page is mutable and its first-revision timestamp was "
                "not captured before the bounded audit stopped."
            )
        if "/latest/" in path:
            return "Moving latest-version documentation with no stable item date."
        if path.lower().endswith(".pdf"):
            return (
                "Authoritative title-page date was not inspected before the "
                "bounded audit stopped."
            )
        if any(
            marker in path
            for marker in (
                "haskell-1.4",
                "haskell-report-1.3",
                "haskell-library-1.4",
                "haskell98-report",
                "/onlinereport/",
                "/ghc/docs/6.8.3/",
            )
        ):
            return (
                "The version is identifiable, but an authoritative exact "
                "release/publication date was not captured in this pass."
            )
        return (
            "Mutable or legacy hosted page without captured authoritative "
            "publication/creation metadata."
        )
    return "No defensible date evidence was captured."


def main() -> None:
    urls: list[str] = []
    for line in INPUT.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) != 3 or fields[1] != "indexed":
            continue
        host = urlsplit(fields[0]).hostname
        if host in HOSTS:
            urls.append(fields[0])

    if len(urls) != len(set(urls)):
        raise ValueError("Target URL set unexpectedly contains duplicates")

    results: list[dict[str, str | None]] = []
    for url in sorted(urls):
        host = urlsplit(url).hostname
        assert host is not None
        if host == "book.realworldhaskell.org":
            results.append(
                {
                    "url": url,
                    "status": "published",
                    "date": "2008-11",
                    "evidence": (
                        "The official online home page states that the first "
                        "edition was released in November 2008; this URL is a "
                        "page in that first-edition online book."
                    ),
                    "source": "https://book.realworldhaskell.org/",
                }
            )
        elif url == LEAN_THESIS:
            results.append(
                {
                    "url": url,
                    "status": "publication",
                    "date": "2023-05-26",
                    "evidence": (
                        "The thesis title page explicitly gives the oral "
                        "examination date as 26.05.2023. The PDF metadata year "
                        "1979 is spurious and was rejected."
                    ),
                    "source": url,
                }
            )
        elif url == HASKELL_GHC_BLOG:
            results.append(
                {
                    "url": url,
                    "status": "published",
                    "date": "2021-07-09",
                    "evidence": (
                        "The GHC blog's canonical path encodes the article "
                        "publication date as 20210709."
                    ),
                    "source": url,
                }
            )
        elif url == HASKELL_PIPERMAIL_PDF:
            results.append(
                {
                    "url": url,
                    "status": "archived",
                    "date": "2009-04-24",
                    "evidence": (
                        "The Haskell mailing-list attachment archive path "
                        "places this attachment under 20090424."
                    ),
                    "source": url,
                }
            )
        else:
            results.append(
                {
                    "url": url,
                    "status": None,
                    "date": None,
                    "evidence": None,
                    "source": None,
                    "reason": unresolved_reason(url, host),
                }
            )

    resolved = [item for item in results if item["status"] and item["date"]]
    unresolved = [item for item in results if not item["status"] and not item["date"]]
    if len(resolved) + len(unresolved) != len(results):
        raise ValueError("A result has only one of status/date")

    payload = {
        "scope": {
            "input": "io_links.md",
            "selection": "current indexed rows on six requested hosts",
            "hosts": sorted(HOSTS),
            "network_expansion_stopped": True,
        },
        "summary": {
            "targets": len(results),
            "resolved": len(resolved),
            "unresolved": len(unresolved),
            "targets_by_host": dict(
                sorted(Counter(urlsplit(item["url"]).hostname for item in results).items())
            ),
            "resolved_by_host": dict(
                sorted(Counter(urlsplit(item["url"]).hostname for item in resolved).items())
            ),
        },
        "results": results,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(payload["summary"], indent=2))


if __name__ == "__main__":
    main()

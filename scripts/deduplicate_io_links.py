#!/usr/bin/env python3
"""Remove machine-format DBLP siblings and trivial URL aliases."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit


DBLP_HOSTS = {"dblp.org", "dblp.dagstuhl.de"}
DBLP_SUFFIX = re.compile(r"\.(?:html|bib|ris|xml|rdf|nt|ttl|txt)$", re.I)
ARXIV = re.compile(
    r"^https?://(?:www\.)?arxiv\.org/(?:abs|pdf|html|format)/"
    r"([^?#]+?)(?:\.pdf)?$",
    re.I,
)
DOCUMENT_SUFFIX = re.compile(
    r"(?P<suffix>\.(?:pdf|ps|dvi|tex|html?|txt)(?:\.gz)?)$", re.I
)
ACM_DOI = re.compile(
    r"^https?://(?:www\.)?dl\.acm\.org/doi/(?:abs/|pdf/)?(10\.[^?#]+)", re.I
)
HACKAGE_HOSTS = {
    "hackage.haskell.org",
    "hackage-content.haskell.org",
    "hackage-content-origin.haskell.org",
}
PACKAGE_INDEX_HOSTS = {
    "app.unpkg.com",
    "build.opensuse.org",
    "central.sonatype.com",
    "clojars.org",
    "cpm.curry-lang.org",
    "crates.io",
    "docs.rs",
    "elixir.hexdocs.pm",
    "dev.flora.pm",
    "flora.pm",
    "hackage-content-origin.haskell.org",
    "hackage-content.haskell.org",
    "hackage-origin.haskell.org",
    "hackage-search.serokell.io",
    "hackage.haskell.org",
    "haskell.libhunt.com",
    "hex.pm",
    "hexdocs.pm",
    "index.scala-lang.org",
    "iteratee.hackage.haskell.org",
    "javadoc.io",
    "libraries.io",
    "mvnrepository.com",
    "mynixos.com",
    "npm.io",
    "npmjs.com",
    "nuget.org",
    "opam-5.ocaml.org",
    "opam.ocaml.org",
    "opam.ocamllabs.io",
    "package.elm-lang.org",
    "packagehub.suse.com",
    "packages.cachyos.org",
    "packages.debian.org",
    "packages.ecosyste.ms",
    "packages.fedoraproject.org",
    "packages.gentoo.org",
    "packages.guix.gnu.org",
    "packages.ubuntu.com",
    "packagist.org",
    "packagist.uihtm.com",
    "pkg.go.dev",
    "pkgs.racket-lang.org",
    "pub.dev",
    "pursuit.purescript.org",
    "pursuit.purerl.fun",
    "pypi.org",
    "repos.ecosyste.ms",
    "rpmfind.net",
    "sources.debian.org",
    "stackage.org",
    "swift.libhunt.com",
    "swiftpackageregistry.com",
    "www.javadoc.io",
    "www.jsdelivr.com",
    "www.libhunt.com",
    "www.npmjs.com",
    "www.nuget.org",
    "www.rpmfind.net",
    "www.stackage.org",
}
LOW_VALUE_HOSTS = {
    "academia.edu",
    "dblp.uni-trier.de",
    "dokumen.pub",
    "exchangetuts.com",
    "export.arxiv.org",
    "news.ycombinator.com",
    "paperzz.com",
    "reddit.com",
    "researchgate.net",
    "riptutorial.com",
    "sambuz.com",
    "scispace.com",
    "scribd.com",
    "slideplayer.com",
    "slideserve.com",
    "slideshare.net",
    "softwarepatternslexicon.com",
    "stackoverflow.com",
    "studylib.net",
    "www.academia.edu",
    "www.reddit.com",
    "www.researchgate.net",
    "www.sambuz.com",
    "www.scribd.com",
    "www.slideplayer.com",
    "www.slideserve.com",
    "www.slideshare.net",
    "www.stackoverflow.com",
    "www.stackprinter.com",
}
PACKAGE_VERSION = re.compile(
    r"^(?P<name>.+)-(?P<version>\d+(?:\.\d+)+(?:[-+][A-Za-z0-9.-]+)?)$"
)
TRACKING = {
    "ref",
    "source",
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
}


def dblp_key(url: str) -> str | None:
    parsed = urlsplit(url)
    if (parsed.hostname or "").casefold() not in DBLP_HOSTS:
        return None
    if not parsed.path.startswith("/rec/"):
        return None
    return DBLP_SUFFIX.sub("", parsed.path.removeprefix("/rec/").rstrip("/"))


def alias_key(url: str) -> tuple[str, str, tuple[tuple[str, str], ...]]:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").casefold()
    if host.startswith("www."):
        host = host[4:]
    query = tuple(
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.casefold() not in TRACKING
    )
    return host, parsed.path.rstrip("/") or "/", query


def arxiv_key(url: str) -> str | None:
    match = ARXIV.match(url)
    return match.group(1) if match else None


def acm_key(url: str) -> str | None:
    match = ACM_DOI.match(url)
    return match.group(1) if match else None


def document_key(url: str) -> tuple[str, str, str] | None:
    parsed = urlsplit(url)
    match = DOCUMENT_SUFFIX.search(parsed.path)
    if not match:
        return None
    host = (parsed.hostname or "").casefold().removeprefix("www.")
    return host, DOCUMENT_SUFFIX.sub("", parsed.path), parsed.query


def document_format(url: str) -> str | None:
    match = DOCUMENT_SUFFIX.search(urlsplit(url).path)
    return match.group("suffix").casefold() if match else None


def document_url_rank(url: str) -> tuple[int, int, int, int]:
    suffix = document_format(url) or ""
    format_rank = {
        ".html": 7,
        ".htm": 7,
        ".pdf": 6,
        ".pdf.gz": 5,
        ".ps": 4,
        ".ps.gz": 3,
        ".dvi": 2,
        ".dvi.gz": 1,
        ".tex": 0,
        ".txt": 0,
    }.get(suffix, 0)
    parsed = urlsplit(url)
    return (
        format_rank,
        int(parsed.scheme == "https"),
        int(not (parsed.hostname or "").startswith("www.")),
        -len(url),
    )


def hackage_canonical(url: str) -> str | None:
    parsed = urlsplit(url)
    if (parsed.hostname or "").casefold() not in HACKAGE_HOSTS:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2 or parts[0] != "package":
        return None

    segment = re.sub(r"\.tar\.gz$", "", parts[1], flags=re.I)
    match = PACKAGE_VERSION.match(segment)
    remainder = parts[2:]
    if match:
        package = match.group("name")
        if remainder and re.fullmatch(rf"{re.escape(segment)}\.tar\.gz", remainder[0]):
            remainder = []
    else:
        package = segment
        if remainder and re.fullmatch(r"\d+(?:\.\d+)+", remainder[0]):
            remainder = remainder[1:]
        if remainder and remainder[-1].casefold().endswith(".tar.gz"):
            remainder = []

    path = "/".join(["package", package, *remainder])
    return f"https://hackage.haskell.org/{path}"


def hackage_metadata_rank(row: list[str]) -> tuple[int, str, int]:
    status = row[1]
    status_rank = {
        "publication": 5,
        "published": 5,
        "released": 5,
        "uploaded": 5,
        "authored": 4,
        "created": 3,
        "updated": 2,
        "modified": 2,
        "accessed": 0,
    }.get(status, 1)
    return int(status != "accessed"), row[2], status_rank


def is_excluded_domain(url: str) -> bool:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").casefold()
    path = parsed.path.casefold()
    return (
        host in PACKAGE_INDEX_HOSTS
        or host in LOW_VALUE_HOSTS
        or any(host.endswith(f".{root}") for root in LOW_VALUE_HOSTS)
        or host == "github.com"
        or host.endswith(".github.com")
        or host.endswith(".pypi.org")
        or host.endswith(".nuget.org")
        or (host == "archlinux.org" and path.startswith("/packages/"))
        or (host == "www.archlinux.de" and path.startswith("/packages/"))
        or (host == "ocaml.org" and path.startswith("/p/"))
        or (host == "rocq-prover.org" and path.startswith(("/p/", "/packages/")))
        or (host == "www.haskell.org" and path.startswith("/hackage/package/"))
        or (host == "foundation.haskell.org" and path.startswith("/package/"))
        or (host == "haskell-docs.netlify.app" and path.startswith("/packages/"))
        or (host == "ocaml.github.io" and "/packages/" in path)
        or (host == "input-output-hk.github.io" and "/packages/package/" in path)
        or "hackage-content.haskell.org/package/" in path
        or "/pool/" in path
    )


def precision(date: str) -> tuple[int, str]:
    return date.count("-"), date


def row_rank(row: list[str]) -> tuple[int, int, int, int, str]:
    url, status, date = row
    parsed = urlsplit(url)
    status_rank = {
        "publication": 5,
        "published": 5,
        "released": 5,
        "uploaded": 4,
        "authored": 4,
        "created": 3,
        "updated": 2,
        "modified": 2,
        "accessed": 0,
    }.get(status, 1)
    return (
        status_rank,
        precision(date)[0],
        int(parsed.scheme == "https"),
        int(not (parsed.hostname or "").startswith("www.")),
        -len(url),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, default=Path("io_links.md"))
    parser.add_argument(
        "--report", type=Path, default=Path("scratch/io-links-deduplication.json")
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    lines = args.file.read_text(encoding="utf-8").splitlines()
    title = next((line for line in lines if line.startswith("# ")), "# IO Monad Links")
    rows = [line.split("\t") for line in lines if len(line.split("\t")) == 3]
    input_records = len(rows)
    removed: list[dict[str, str]] = []
    retained_rows: list[list[str]] = []
    for row in rows:
        if is_excluded_domain(row[0]):
            removed.append(
                {"url": row[0], "kept": "", "reason": "excluded domain"}
            )
        else:
            retained_rows.append(row)
    rows = retained_rows

    dblp_groups: dict[str, list[list[str]]] = defaultdict(list)
    acm_groups: dict[str, list[list[str]]] = defaultdict(list)
    arxiv_groups: dict[str, list[list[str]]] = defaultdict(list)
    ordinary: list[list[str]] = []
    for row in rows:
        key = dblp_key(row[0])
        if key is not None:
            dblp_groups[key].append(row)
            continue
        key = acm_key(row[0])
        if key is not None:
            acm_groups[key].append(row)
            continue
        key = arxiv_key(row[0])
        if key is not None:
            arxiv_groups[key].append(row)
            continue
        ordinary.append(row)

    kept: list[list[str]] = []
    for key, group in sorted(dblp_groups.items()):
        winner = max(group, key=row_rank)
        canonical = [f"https://dblp.org/rec/{key}.html", winner[1], winner[2]]
        kept.append(canonical)
        for row in group:
            if row != canonical:
                removed.append(
                    {"url": row[0], "kept": canonical[0], "reason": "DBLP sibling"}
                )

    for key, group in sorted(arxiv_groups.items()):
        winner = max(group, key=row_rank)
        canonical = [f"https://arxiv.org/abs/{key}", winner[1], winner[2]]
        kept.append(canonical)
        for row in group:
            if row != canonical:
                removed.append(
                    {"url": row[0], "kept": canonical[0], "reason": "arXiv sibling"}
                )

    for key, group in sorted(acm_groups.items()):
        winner = max(group, key=row_rank)
        canonical = [f"https://dl.acm.org/doi/{key}", winner[1], winner[2]]
        kept.append(canonical)
        for row in group:
            if row != canonical:
                removed.append(
                    {"url": row[0], "kept": canonical[0], "reason": "ACM DOI sibling"}
                )

    hackage_groups: dict[str, list[list[str]]] = defaultdict(list)
    no_hackage: list[list[str]] = []
    for row in ordinary:
        canonical = hackage_canonical(row[0])
        if canonical is None:
            no_hackage.append(row)
        else:
            hackage_groups[canonical].append(row)

    ordinary = no_hackage
    for canonical, group in hackage_groups.items():
        metadata = max(group, key=hackage_metadata_rank)
        winner = [canonical, metadata[1], metadata[2]]
        kept.append(winner)
        for row in group:
            if row != winner:
                removed.append(
                    {
                        "url": row[0],
                        "kept": canonical,
                        "reason": "versioned Hackage sibling",
                    }
                )

    document_groups: dict[tuple[str, str, str], list[list[str]]] = defaultdict(list)
    no_document: list[list[str]] = []
    for row in ordinary:
        key = document_key(row[0])
        if key is None:
            no_document.append(row)
        else:
            document_groups[key].append(row)

    ordinary = no_document
    for group in document_groups.values():
        if len({document_format(row[0]) for row in group}) < 2:
            ordinary.extend(group)
            continue
        url_winner = max(group, key=lambda row: document_url_rank(row[0]))
        metadata_winner = max(group, key=row_rank)
        canonical = [url_winner[0], metadata_winner[1], metadata_winner[2]]
        kept.append(canonical)
        for row in group:
            if row != canonical:
                removed.append(
                    {
                        "url": row[0],
                        "kept": canonical[0],
                        "reason": "alternate document format",
                    }
                )

    alias_groups: dict[tuple[str, str, tuple[tuple[str, str], ...]], list[list[str]]] = (
        defaultdict(list)
    )
    for row in ordinary:
        alias_groups[alias_key(row[0])].append(row)

    for group in alias_groups.values():
        winner = max(group, key=row_rank)
        kept.append(winner)
        for row in group:
            if row is not winner:
                removed.append(
                    {"url": row[0], "kept": winner[0], "reason": "trivial URL alias"}
                )

    human_urls = {row[0].rstrip("/") for row in kept}
    filtered: list[list[str]] = []
    for row in kept:
        parent = re.sub(r"/(?:bibtex|oembed)/?$", "", row[0], flags=re.I)
        if parent != row[0].rstrip("/") and parent in human_urls:
            removed.append(
                {"url": row[0], "kept": parent, "reason": "machine metadata endpoint"}
            )
        else:
            filtered.append(row)
    kept = filtered

    kept.sort(key=lambda row: row[2])
    report = {
        "input_records": input_records,
        "output_records": len(kept),
        "removed_records": input_records - len(kept),
        "dblp_works": len(dblp_groups),
        "acm_works": len(acm_groups),
        "arxiv_works": len(arxiv_groups),
        "hackage_targets": len(hackage_groups),
        "document_stems": len(document_groups),
        "removed": removed,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if args.apply:
        args.file.write_text(
            "\n".join([title, *("\t".join(row) for row in kept)]) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    print({key: value for key, value in report.items() if key != "removed"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Resolve indexed CiteSeerX links against the official 2017 metadata dump."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import time
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests


ARCHIVE_ROOT = (
    "https://archive.org/download/citeseerx-csx_citegraph.2017-03-31"
)
CHECKSUM_SOURCE = f"{ARCHIVE_ROOT}/citeseerx_checksums.tsv.gz"
PAPER_SOURCE = f"{ARCHIVE_ROOT}/citeseerx_papers.tsv.gz"
AUTHOR_SOURCE = f"{ARCHIVE_ROOT}/citeseerx_authors.tsv.gz"
CURRENT_YEAR = date.today().year
SHA1_RE = re.compile(r"^[0-9a-f]{40}$", re.I)
LEGACY_ID_RE = re.compile(r"^10\.1\.1\.\d+\.\d+$")
VALID_YEAR_RE = re.compile(r"^(18|19|20)\d{2}$")
SNAPSHOT_YEAR = 2017


def clean(value: str) -> str:
    value = value.strip()
    return "" if value == r"\N" else value


def current_targets(path: Path) -> list[dict]:
    targets: list[dict] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        parts = line.split("\t")
        if len(parts) != 3 or parts[1] != "indexed":
            continue
        parsed = urlparse(parts[0])
        if parsed.hostname not in {
            "citeseerx.ist.psu.edu",
            "www.citeseerx.ist.psu.edu",
        }:
            continue
        doi = parse_qs(parsed.query).get("doi", [""])[0].strip()
        identifier_type = (
            "sha1"
            if SHA1_RE.fullmatch(doi)
            else "legacy"
            if LEGACY_ID_RE.fullmatch(doi)
            else "unknown"
        )
        targets.append(
            {
                "url": parts[0],
                "line": line_number,
                "identifier": doi,
                "identifier_type": identifier_type,
            }
        )
    return targets


def checksum_matches(path: Path, wanted: set[str]) -> dict[str, set[str]]:
    matches: dict[str, set[str]] = defaultdict(set)
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            sha1, separator, remainder = line.partition("\t")
            if not separator or sha1.lower() not in wanted:
                continue
            legacy_id = remainder.partition("\t")[0].strip()
            if LEGACY_ID_RE.fullmatch(legacy_id):
                matches[sha1.lower()].add(legacy_id)
    return matches


def paper_matches(path: Path, wanted: set[str]) -> dict[str, list[dict]]:
    matches: dict[str, list[dict]] = defaultdict(list)
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            paper_id, separator, remainder = line.partition("\t")
            if not separator or paper_id not in wanted:
                continue
            values = [paper_id, *remainder.rstrip("\n").split("\t")]
            values += [""] * (8 - len(values))
            matches[paper_id].append(
                {
                    "id": clean(values[0]),
                    "title": clean(values[1]),
                    "type": clean(values[2]),
                    "venue": clean(values[3]),
                    "year": clean(values[4]),
                    "volume": clean(values[5]),
                    "issue": clean(values[6]),
                    "pages": clean(values[7]),
                }
            )
    return matches


def author_matches(path: Path, wanted: set[str]) -> dict[str, list[str]]:
    matches: dict[str, list[tuple[int, str]]] = defaultdict(list)
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            paper_id, separator, remainder = line.partition("\t")
            if not separator or paper_id not in wanted:
                continue
            position, separator, name = remainder.rstrip("\n").partition("\t")
            if not separator or not clean(name):
                continue
            try:
                order = int(position)
            except ValueError:
                order = 9999
            matches[paper_id].append((order, clean(name)))
    return {
        paper_id: [name for _, name in sorted(values)]
        for paper_id, values in matches.items()
    }


def valid_year(value: str) -> bool:
    return bool(VALID_YEAR_RE.fullmatch(value)) and 1800 <= int(value) <= SNAPSHOT_YEAR


def evidence_for(record: dict) -> str:
    details = [f"CiteSeerX paper record {record['id']}", f"year {record['year']}"]
    if record["title"]:
        details.append(f"title: {record['title']}")
    if record["type"]:
        details.append(f"type: {record['type']}")
    if record["venue"]:
        details.append(f"venue: {record['venue']}")
    return "; ".join(details)


def normalized_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(character for character in value if not unicodedata.combining(character))
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def meaningful_title(value: str) -> bool:
    normalized = normalized_text(value)
    if not normalized:
        return False
    boilerplate = {
        "2012",
        "1st year transfer dissertation",
        "and the committee on graduate studies",
        "completed on",
        "contents",
        "contents i",
        "selected papers",
        "swansea",
    }
    if normalized in boilerplate:
        return False
    return not normalized.startswith(
        ("department of ", "recommended citation ", "school ipa ")
    )


def author_tokens(names: list[str]) -> set[str]:
    excluded = {
        "author",
        "authors",
        "department",
        "group",
        "investigator",
        "laboratory",
        "research",
        "university",
    }
    return {
        token
        for name in names
        for token in normalized_text(name).split()
        if len(token) > 1 and token not in excluded
    }


def format_date_parts(parts: object) -> str | None:
    if not isinstance(parts, list) or not parts or not isinstance(parts[0], list):
        return None
    values = parts[0]
    if not values or not isinstance(values[0], int):
        return None
    if not 1800 <= values[0] <= CURRENT_YEAR:
        return None
    if len(values) >= 3 and all(isinstance(value, int) for value in values[:3]):
        try:
            return date(values[0], values[1], values[2]).isoformat()
        except ValueError:
            return None
    if len(values) >= 2 and isinstance(values[1], int) and 1 <= values[1] <= 12:
        return f"{values[0]:04d}-{values[1]:02d}"
    return f"{values[0]:04d}"


def crossref_query(
    session: requests.Session,
    cache_dir: Path,
    title: str,
    timeout: float,
    offline: bool,
) -> tuple[dict | None, str | None]:
    key = hashlib.sha256(normalized_text(title).encode()).hexdigest()
    cache_path = cache_dir / f"{key}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8")), None
    if offline:
        return None, "offline-cache-miss"
    try:
        response = session.get(
            "https://api.crossref.org/works",
            params={
                "query.title": title,
                "rows": 10,
                "select": (
                    "DOI,title,author,published,published-print,published-online,"
                    "issued,created,type,container-title,score"
                ),
            },
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        cache_path.write_text(
            json.dumps(payload, ensure_ascii=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        time.sleep(0.5)
        return payload, None
    except (requests.RequestException, ValueError) as exc:
        return None, f"{type(exc).__name__}: {exc}"


def crossref_match(
    payload: dict, title: str, cite_authors: list[str]
) -> tuple[dict | None, str | None]:
    wanted_title = normalized_text(title)
    wanted_authors = author_tokens(cite_authors)
    if not wanted_title or not wanted_authors:
        return None, "CiteSeerX title or author metadata is insufficient for matching"
    items = payload.get("message", {}).get("items", [])
    candidates = []
    for item in items:
        item_titles = item.get("title") or []
        if not item_titles or normalized_text(item_titles[0]) != wanted_title:
            continue
        crossref_families = [
            author.get("family", "") for author in item.get("author", [])
        ]
        if not (wanted_authors & author_tokens(crossref_families)):
            continue
        publication = (
            item.get("published")
            or item.get("published-online")
            or item.get("published-print")
            or item.get("issued")
        )
        publication_date = format_date_parts(
            publication.get("date-parts") if isinstance(publication, dict) else None
        )
        if not publication_date:
            continue
        candidates.append((item, publication_date, crossref_families))
    distinct = {(item.get("DOI"), value) for item, value, _ in candidates}
    if not candidates:
        return None, "No exact Crossref title-and-author match with a publication date"
    if len(distinct) > 1:
        return None, "Multiple exact Crossref title-and-author matches disagree"
    item, publication_date, crossref_families = candidates[0]
    return (
        {
            "date": publication_date,
            "doi": item.get("DOI"),
            "title": (item.get("title") or [""])[0],
            "authors": crossref_families,
            "type": item.get("type"),
            "container_title": (item.get("container-title") or [""])[0],
        },
        None,
    )


def resolve(
    target: dict,
    checksums: dict[str, set[str]],
    papers: dict[str, list[dict]],
    authors: dict[str, list[str]],
) -> dict:
    result = {
        "url": target["url"],
        "status": "unresolved",
        "date": None,
        "evidence": None,
        "source": None,
        "unresolved_reason": None,
        "evidence_quality": None,
        "line": target["line"],
    }
    identifier = target["identifier"]
    if target["identifier_type"] == "sha1":
        record_ids = sorted(checksums.get(identifier.lower(), set()))
        result["source"] = [CHECKSUM_SOURCE, PAPER_SOURCE]
        if not record_ids:
            result["unresolved_reason"] = (
                "SHA-1 identifier is absent from the 2017 CiteSeerX checksum dump"
            )
            return result
    elif target["identifier_type"] == "legacy":
        record_ids = [identifier]
        result["source"] = PAPER_SOURCE
    else:
        result["source"] = target["url"]
        result["evidence"] = f"Unrecognized doi query value: {identifier}"
        result["unresolved_reason"] = "URL has no recognized CiteSeerX identifier"
        return result

    records = [record for record_id in record_ids for record in papers.get(record_id, [])]
    result["matched_record_ids"] = record_ids
    if not records:
        result["unresolved_reason"] = (
            "Mapped identifier has no record in the 2017 CiteSeerX paper dump"
        )
        return result

    result["candidate_records"] = records
    result["candidate_authors"] = {
        record_id: authors.get(record_id, []) for record_id in record_ids
    }
    dated_records = [
        record
        for record in records
        if valid_year(record["year"]) and meaningful_title(record["title"])
    ]
    years = sorted({record["year"] for record in dated_records})
    if not years:
        raw_years = sorted({record["year"] for record in records if record["year"]})
        result["evidence"] = "; ".join(evidence_for(record) for record in records)
        if raw_years:
            result["evidence"] += f"; unusable year values: {', '.join(raw_years)}"
        result["unresolved_reason"] = (
            "CiteSeerX paper metadata has no trustworthy title-and-year pair"
        )
        return result
    if len(years) != 1:
        result["evidence"] = "; ".join(evidence_for(record) for record in dated_records)
        result["unresolved_reason"] = (
            "Exact-content CiteSeerX records disagree on publication year: "
            + ", ".join(years)
        )
        return result

    selected = next(record for record in dated_records if record["year"] == years[0])
    result.update(
        status="publication",
        date=years[0],
        evidence=evidence_for(selected),
        unresolved_reason=None,
        evidence_quality="medium",
    )
    if len(records) > 1:
        result["evidence"] += (
            f"; {len(records)} exact-content record(s) agree on this year"
        )
    return result


def within_one_edit(left: str, right: str) -> bool:
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        return sum(a != b for a, b in zip(left, right)) <= 1
    if len(left) > len(right):
        left, right = right, left
    short_index = long_index = edits = 0
    while short_index < len(left) and long_index < len(right):
        if left[short_index] == right[long_index]:
            short_index += 1
            long_index += 1
            continue
        edits += 1
        long_index += 1
        if edits > 1:
            return False
    edits += len(right) - long_index
    return edits <= 1


def note_possible_identifier_corrections(
    targets: list[dict], results: list[dict], mapped_sha1s: set[str]
) -> None:
    for target, result in zip(targets, results):
        if result.get("date") or not target["identifier"]:
            continue
        identifier = target["identifier"].lower()
        candidates = sorted(
            sha1
            for sha1 in mapped_sha1s
            if sha1 != identifier and within_one_edit(identifier, sha1)
        )
        if len(candidates) != 1:
            continue
        result["possible_identifier_correction"] = candidates[0]
        detail = (
            f"Identifier is one edit from mapped CiteSeerX SHA-1 {candidates[0]}; "
            "date was not inferred from a likely typo"
        )
        result["evidence"] = (
            f"{result['evidence']}; {detail}" if result.get("evidence") else detail
        )
        if result.get("source") is None:
            result["source"] = CHECKSUM_SOURCE


def enhance_with_crossref(
    results: list[dict],
    session: requests.Session,
    cache_dir: Path,
    timeout: float,
    offline: bool,
) -> tuple[int, list[str]]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    enhanced = 0
    errors: list[str] = []
    consecutive_errors = 0
    for result in results:
        records = result.get("candidate_records") or []
        if not records:
            continue
        record = next((item for item in records if item.get("title")), None)
        if not record:
            continue
        authors = [
            name
            for values in (result.get("candidate_authors") or {}).values()
            for name in values
        ]
        payload, error = crossref_query(
            session, cache_dir, record["title"], timeout, offline
        )
        if error:
            if error == "offline-cache-miss":
                result["crossref_match_reason"] = (
                    "Crossref not checked because no cached response is available"
                )
                continue
            result["crossref_api_error"] = error
            errors.append(f"{result['url']}: {error}")
            consecutive_errors += 1
            if consecutive_errors >= 2:
                break
            continue
        consecutive_errors = 0
        match, reason = crossref_match(payload or {}, record["title"], authors)
        result["crossref_match_reason"] = reason
        if not match:
            continue
        doi = match["doi"]
        source = f"https://api.crossref.org/works/{doi}" if doi else "Crossref API"
        result.update(
            status="publication",
            date=match["date"],
            source=[PAPER_SOURCE, AUTHOR_SOURCE, source],
            evidence=(
                f"Exact normalized title and author match in Crossref; "
                f"DOI {doi}; title: {match['title']}; "
                f"authors: {', '.join(match['authors'])}; "
                f"publication date {match['date']}"
            ),
            unresolved_reason=None,
            evidence_quality="high",
            crossref=match,
        )
        enhanced += 1
    return enhanced, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, default=Path("io_links.md"))
    parser.add_argument(
        "--checksums",
        type=Path,
        default=Path("tmp/citeseerx-continuation/citeseerx_checksums.tsv.gz"),
    )
    parser.add_argument(
        "--papers",
        type=Path,
        default=Path("tmp/citeseerx-continuation/citeseerx_papers.tsv.gz"),
    )
    parser.add_argument(
        "--authors",
        type=Path,
        default=Path("tmp/citeseerx-continuation/citeseerx_authors.tsv.gz"),
    )
    parser.add_argument(
        "--crossref-cache",
        type=Path,
        default=Path("tmp/citeseerx-continuation/crossref"),
    )
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--crossref-offline", action="store_true")
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("scratch/citeseerx-continuation-audit.json"),
    )
    args = parser.parse_args()

    targets = current_targets(args.file)
    wanted_sha1s = {
        target["identifier"].lower()
        for target in targets
        if target["identifier_type"] == "sha1"
    }
    checksums = checksum_matches(args.checksums, wanted_sha1s)
    wanted_ids = {
        target["identifier"]
        for target in targets
        if target["identifier_type"] == "legacy"
    }
    for values in checksums.values():
        wanted_ids.update(values)
    papers = paper_matches(args.papers, wanted_ids)
    authors = author_matches(args.authors, wanted_ids)
    results = [resolve(target, checksums, papers, authors) for target in targets]
    note_possible_identifier_corrections(targets, results, set(checksums))
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "io-links-date-audit/1.0 "
                "(https://github.com/alexyorke/alexyorke.github.io)"
            )
        }
    )
    enhanced, errors = enhance_with_crossref(
        results,
        session,
        args.crossref_cache,
        args.timeout,
        args.crossref_offline,
    )

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(results, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    resolved = sum(bool(item["date"]) for item in results)
    print(
        f"{len(results)} CiteSeerX indexed rows; "
        f"{resolved} resolved; {len(results) - resolved} unresolved; "
        f"{enhanced} exact Crossref matches; {len(errors)} API errors"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

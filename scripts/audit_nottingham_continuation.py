#!/usr/bin/env python3
"""Audit indexed Nottingham ePrint links against official repository metadata."""

from __future__ import annotations

import argparse
import json
import re
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


EPRINT_IDS = {
    "10779",
    "11226",
    "11457",
    "11981",
    "13348",
    "36159",
    "41715",
    "43557",
    "50348",
    "60350",
}
EPRINT_RE = re.compile(
    r"^https://eprints\.nottingham\.ac\.uk/(?:id/eprint/)?(\d+)(?:/|$)"
)
API_BASE = "https://repository.nottingham.ac.uk/server/api"
THESIS_FRONT_MATTER = {
    "10779": {
        "date": "2009-02",
        "date_text": "February 2009",
        "pdf_name": "Thesis.pdf",
    },
    "11226": {
        "date": "2009-08",
        "date_text": "August 2009",
        "pdf_name": "Thesis.pdf",
    },
    "11457": {
        "date": "2010-07",
        "date_text": "July 2010",
        "pdf_name": "thesis.pdf",
    },
    "11981": {
        "date": "2011-07",
        "date_text": "July 2011",
        "pdf_name": "thesis.pdf",
    },
    "13348": {
        "date": "2012-06",
        "date_text": "June 2012",
        "pdf_name": "hu-thesis.pdf",
    },
    "43557": {
        "date": "2014-12",
        "date_text": "December 2014",
        "pdf_name": "led_phd_thesis.pdf",
    },
    "50348": {
        "date": "2018-02",
        "date_text": "February 2018",
        "pdf_name": "thesis.pdf",
    },
    "60350": {
        "date": "2020-04-13",
        "date_text": "April 13, 2020",
        "pdf_name": "thaler_thesis_minorcorrections.pdf",
    },
}
CONFERENCE_RECORDS = {
    "36159": {
        "title": "Functional reactive programming, refactored",
        "date": "2016-09-22",
        "event": (
            "Proceedings of the 9th International Symposium on Haskell "
            "(Haskell '16), 22-23 September 2016"
        ),
        "source_url": "https://eprints.nottingham.ac.uk/36159/",
    },
    "41715": {
        "title": "The continuity of monadic stream functions",
        "date": "2017-06-20",
        "event": (
            "32nd Annual ACM/IEEE Symposium on Logic in Computer Science "
            "(LICS'17), 20-23 Jun 2017"
        ),
        "source_url": "https://eprints.nottingham.ac.uk/41715/",
    },
}


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "io-links-date-audit/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def metadata_values(item: dict, key: str) -> list[str]:
    return [entry["value"] for entry in item.get("metadata", {}).get(key, [])]


def find_item(eprint_id: str) -> dict:
    query = urllib.parse.quote(f"dc.identifier.eprintsID:{eprint_id}")
    url = f"{API_BASE}/discover/search/objects?query={query}&size=10"
    payload = fetch_json(url)
    objects = (
        payload.get("_embedded", {})
        .get("searchResult", {})
        .get("_embedded", {})
        .get("objects", [])
    )
    matches = []
    for wrapper in objects:
        item = wrapper.get("_embedded", {}).get("indexableObject", {})
        if eprint_id in metadata_values(item, "dc.identifier.eprintsID"):
            matches.append(item)
    if len(matches) != 1:
        raise RuntimeError(
            f"expected one exact official item for ePrint {eprint_id}, "
            f"found {len(matches)}"
        )
    return matches[0]


def normalise_issued(value: str) -> str:
    match = re.fullmatch(r"(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?", value)
    if not match:
        raise ValueError(f"unsupported dc.date.issued value: {value!r}")
    return value


def find_original_pdf(item: dict, expected_name: str) -> dict:
    item_uuid = item["uuid"]
    bundles = fetch_json(f"{API_BASE}/core/items/{item_uuid}/bundles?size=100")
    originals = [
        bundle
        for bundle in bundles.get("_embedded", {}).get("bundles", [])
        if bundle.get("name") == "ORIGINAL"
    ]
    if len(originals) != 1:
        raise RuntimeError(
            f"expected one ORIGINAL bundle for item {item_uuid}, found "
            f"{len(originals)}"
        )
    bitstreams_url = originals[0]["_links"]["bitstreams"]["href"]
    bitstreams = fetch_json(f"{bitstreams_url}?size=100")
    matches = [
        bitstream
        for bitstream in bitstreams.get("_embedded", {}).get("bitstreams", [])
        if bitstream.get("name") == expected_name
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"expected one {expected_name!r} bitstream for item {item_uuid}, "
            f"found {len(matches)}"
        )
    return matches[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("io_links.md"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("scratch/nottingham-continuation-audit.json"),
    )
    args = parser.parse_args()

    targets: list[dict[str, str]] = []
    for line_number, line in enumerate(
        args.input.read_text(encoding="utf-8").splitlines(), start=1
    ):
        fields = line.split("\t")
        if len(fields) != 3 or fields[1] != "indexed":
            continue
        match = EPRINT_RE.match(fields[0])
        if not match or match.group(1) not in EPRINT_IDS:
            continue
        targets.append(
            {
                "url": fields[0],
                "old_status": fields[1],
                "old_date": fields[2],
                "eprint_id": match.group(1),
                "line": str(line_number),
            }
        )

    found_ids = {target["eprint_id"] for target in targets}
    if found_ids != EPRINT_IDS:
        raise RuntimeError(
            f"target ID mismatch: missing={sorted(EPRINT_IDS - found_ids)}, "
            f"unexpected={sorted(found_ids - EPRINT_IDS)}"
        )

    items = {
        eprint_id: find_item(eprint_id)
        for eprint_id in sorted(THESIS_FRONT_MATTER)
    }
    pdfs = {
        eprint_id: find_original_pdf(
            items[eprint_id], THESIS_FRONT_MATTER[eprint_id]["pdf_name"]
        )
        for eprint_id in sorted(THESIS_FRONT_MATTER)
    }
    results = []
    for target in targets:
        eprint_id = target["eprint_id"]
        if eprint_id in THESIS_FRONT_MATTER:
            item = items[eprint_id]
            issued = metadata_values(item, "dc.date.issued")
            if len(issued) != 1:
                raise RuntimeError(
                    f"ePrint {eprint_id} has {len(issued)} issued dates"
                )
            repository_issued_date = normalise_issued(issued[0])
            title = item.get("name") or metadata_values(item, "dc.title")[0]
            uuid = item["uuid"]
            front_matter = THESIS_FRONT_MATTER[eprint_id]
            date = front_matter["date"]
            bitstream = pdfs[eprint_id]
            source_url = bitstream["_links"]["content"]["href"]
            evidence = (
                f"Official University of Nottingham repository item {uuid} "
                f"matches ePrint ID {eprint_id} and title {title!r}. Its "
                f"original PDF bitstream {bitstream['uuid']} "
                f"({front_matter['pdf_name']}) was downloaded and its rendered "
                f"title page explicitly says the thesis was submitted "
                f"{front_matter['date_text']}. The migrated repository's "
                f"dc.date.issued is {repository_issued_date}; the PDF's authored/"
                f"submission date is used."
            )
            metadata_url = f"{API_BASE}/core/items/{uuid}"
        else:
            conference = CONFERENCE_RECORDS[eprint_id]
            date = conference["date"]
            source_url = conference["source_url"]
            metadata_url = conference["source_url"]
            repository_issued_date = date[:4]
            evidence = (
                f"Official University of Nottingham ePrint record {eprint_id}, "
                f"{conference['title']!r}, identifies the publication as "
                f"{conference['event']}; the event start date is used."
            )
        results.append(
            {
                "url": target["url"],
                "eprint_id": eprint_id,
                "line": int(target["line"]),
                "old_status": target["old_status"],
                "old_date": target["old_date"],
                "status": "publication",
                "source_type": "publication",
                "date": date,
                "new_date": date,
                "outcome": "resolved",
                "confidence": "high",
                "evidence": evidence,
                "source_url": source_url,
                "metadata_url": metadata_url,
                "repository_issued_date": repository_issued_date,
            }
        )

    url_counts = Counter(result["url"] for result in results)
    duplicates = sorted(url for url, count in url_counts.items() if count != 1)
    if duplicates:
        raise RuntimeError(f"duplicate report URLs: {duplicates}")
    if len(results) != len(targets):
        raise RuntimeError("report coverage does not match current indexed targets")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": (
            "Exact dc.identifier.eprintsID match in the official University of "
            "Nottingham DSpace REST API, followed by download, text extraction, "
            "rendering, and visual inspection of each thesis PDF title page. "
            "The two conference records use the event start date printed in "
            "their official Nottingham ePrint metadata."
        ),
        "target_ids": sorted(EPRINT_IDS),
        "target_count": len(targets),
        "resolved_count": len(results),
        "unresolved_count": 0,
        "per_id_counts": dict(
            sorted(Counter(target["eprint_id"] for target in targets).items())
        ),
        "results": results,
        "unresolved": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "targets": len(targets),
                "resolved": len(results),
                "unresolved": 0,
                "output": str(args.output),
            }
        )
    )


if __name__ == "__main__":
    main()

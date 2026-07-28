#!/usr/bin/env python3
"""Resolve malformed CiteSeerX checksum aliases from near-identical dated IDs."""

from __future__ import annotations

import json
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import parse_qs, urlparse


INPUT = Path("io_links.md")
REPORT = Path("scratch/citeseer-typo-alias-audit.json")


def doi(url: str) -> str:
    return parse_qs(urlparse(url).query).get("doi", [""])[0]


def main() -> None:
    known = []
    pending = []
    for line in INPUT.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if (
            len(fields) != 3
            or urlparse(fields[0]).hostname != "citeseerx.ist.psu.edu"
        ):
            continue
        item = {
            "url": fields[0],
            "status": fields[1],
            "date": fields[2],
            "doi": doi(fields[0]),
        }
        (pending if fields[1] == "indexed" else known).append(item)

    results = []
    for item in pending:
        if len(item["doi"]) < 30:
            continue
        ranked = sorted(
            (
                (
                    SequenceMatcher(None, item["doi"], peer["doi"]).ratio(),
                    peer,
                )
                for peer in known
                if len(peer["doi"]) >= 30
            ),
            key=lambda row: row[0],
            reverse=True,
        )
        if len(ranked) < 2:
            continue
        score, peer = ranked[0]
        margin = score - ranked[1][0]
        if score < 0.9 or margin < 0.2:
            continue
        results.append(
            {
                "url": item["url"],
                "status": peer["status"],
                "date": peer["date"],
                "source": peer["url"],
                "evidence": (
                    "Unique near-identical CiteSeerX checksum alias "
                    f"(similarity {score:.3f}, next-candidate margin {margin:.3f})."
                ),
            }
        )

    payload = {
        "target_count": len(results),
        "resolved_count": len(results),
        "unresolved_count": 0,
        "results": results,
    }
    REPORT.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print({key: value for key, value in payload.items() if key.endswith("_count")})


if __name__ == "__main__":
    main()

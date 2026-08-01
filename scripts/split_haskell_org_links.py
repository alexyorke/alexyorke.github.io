#!/usr/bin/env python3
"""Move all haskell.org records from io_links.md into a separate dated list."""

from pathlib import Path
from urllib.parse import urlsplit


SOURCE = Path("io_links.md")
DESTINATION = Path("haskell_org_links.md")


def is_haskell_org(url: str) -> bool:
    host = (urlsplit(url).hostname or "").casefold()
    return host == "haskell.org" or host.endswith(".haskell.org")


def write_list(path: Path, title: str, records: list[list[str]]) -> None:
    records.sort(key=lambda row: row[2])
    path.write_text(
        "\n".join([title, *("\t".join(row) for row in records)]) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> None:
    source_records = [
        line.split("\t")
        for line in SOURCE.read_text(encoding="utf-8").splitlines()
        if len(line.split("\t")) == 3
    ]
    destination_records = (
        [
            line.split("\t")
            for line in DESTINATION.read_text(encoding="utf-8").splitlines()
            if len(line.split("\t")) == 3
        ]
        if DESTINATION.exists()
        else []
    )
    records = list(
        {
            row[0]: row
            for row in [*source_records, *destination_records]
        }.values()
    )
    moved = [row for row in records if is_haskell_org(row[0])]
    retained = [row for row in records if not is_haskell_org(row[0])]
    write_list(SOURCE, "# IO Monad Links", retained)
    write_list(DESTINATION, "# Haskell.org IO Monad Links", moved)
    print(
        {
            "input_records": len(records),
            "retained_records": len(retained),
            "moved_records": len(moved),
        }
    )


if __name__ == "__main__":
    main()

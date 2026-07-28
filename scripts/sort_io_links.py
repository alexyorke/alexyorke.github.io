#!/usr/bin/env python3
"""Sort tab-delimited records by date within each io_links.md section."""

from pathlib import Path


path = Path("io_links.md")
lines = path.read_text(encoding="utf-8").splitlines()
output: list[str] = []
records: list[str] = []


def flush() -> None:
    records.sort(key=lambda line: line.rsplit("\t", 1)[-1])
    output.extend(records)
    records.clear()


for line in lines:
    if line.startswith("## "):
        flush()
        output.append(line)
    elif len(line.split("\t")) == 3:
        records.append(line)
    else:
        flush()
        output.append(line)
flush()

path.write_text("\n".join(output) + "\n", encoding="utf-8", newline="\n")

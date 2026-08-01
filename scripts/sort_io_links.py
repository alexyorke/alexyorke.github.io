#!/usr/bin/env python3
"""Sort every tab-delimited io_links.md record globally by date."""

from pathlib import Path


path = Path("io_links.md")
lines = path.read_text(encoding="utf-8").splitlines()
title = next((line for line in lines if line.startswith("# ")), "# IO Monad Links")
records = [line for line in lines if len(line.split("\t")) == 3]
records.sort(key=lambda line: line.rsplit("\t", 1)[-1])
output = [title, *records]

path.write_text("\n".join(output) + "\n", encoding="utf-8", newline="\n")

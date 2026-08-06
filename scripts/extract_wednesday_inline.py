#!/usr/bin/env python3
"""Extract Sailwave result documents embedded in the legacy Wednesday archive."""

from pathlib import Path
import re

SOURCE = Path(__file__).resolve().parents[2] / "archived_site" / "wednesday-racing-series-archives.html"
DESTINATION = Path(__file__).resolve().parents[1] / "assets" / "wednesday-races"


def result_path(document: str, number: int) -> Path:
    title = re.search(r"<title>(.*?)</title>", document, re.I | re.S)
    label = re.sub(r"<.*?>", "", title.group(1) if title else "").lower()
    year = re.search(r"20(10|11|12|13)", label)
    series = re.search(r"(spring|summer|fall)", label)
    fleet = "420s" if "centerboard" in label or "420" in label else "keelboat"
    return DESTINATION / (year.group(0) if year else "2010") / f"{series.group(1) if series else f'series-{number}'}-{fleet}.html"


content = SOURCE.read_text(encoding="utf-8")
archive = content[content.index("2010-2013 Results"):]
documents = re.findall(r"(<!DOCTYPE.*?</html>)", archive, re.I | re.S)
for number, document in enumerate(documents, start=1):
    destination = result_path(document, number)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(document, encoding="utf-8")

print(f"Extracted {len(documents)} embedded result pages")

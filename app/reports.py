"""CSV export helpers (opens directly in Excel)."""
import csv
from typing import Iterable, Sequence


def export_csv(path: str, headers: Sequence[str], rows: Iterable[Sequence]) -> int:
    count = 0
    # utf-8-sig adds a BOM so Excel shows Urdu / special characters correctly
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(headers)
        for row in rows:
            writer.writerow(["" if v is None else v for v in row])
            count += 1
    return count

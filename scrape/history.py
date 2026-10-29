"""Append-only price history for one scrape run at a time.

Each run is one gzipped CSV under ``<history>/runs/``. Files are never
rewritten. A row is one check-in × nights × board × rooms cell for one
party and one promo, available or unavailable, without the raw offer list.

The default party (``2a3c``) and promo (``none``) keep the original name
``<UTC timestamp>.csv.gz``. Any other combination adds a suffix:

* 2a3c / mhot → ``<UTC timestamp>-mhot.csv.gz``
* 4a1c / none → ``<UTC timestamp>-4a1c.csv.gz``
* 4a1c / mhot → ``<UTC timestamp>-4a1c-mhot.csv.gz``

Snapshots written before these columns exist have no ``party`` or ``promo``
header. Readers treat a missing ``party`` as ``2a3c`` and a missing ``promo``
as ``none``.
"""

from __future__ import annotations

import csv
import gzip
import io
from datetime import datetime, timezone
from pathlib import Path

from scrape.party import DEFAULT_PARTY, DEFAULT_PROMO

HISTORY_FIELDS = [
    "scraped_at",
    "check_in",
    "nights",
    "rooms",
    "board",
    "status",
    "total_price",
    "price_per_night",
    "room_type",
    "party",
    "promo",
]


def normalize_scraped_at(value: datetime | str) -> str:
    """UTC timestamp as ``YYYY-MM-DDTHH:MM:SS[.ffffff]Z``."""
    if isinstance(value, datetime):
        parsed = value
    else:
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError("scraped_at must include a timezone")
    parsed = parsed.astimezone(timezone.utc).replace(tzinfo=timezone.utc)
    if parsed.microsecond:
        return parsed.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")


def run_filename(scraped_at: str, *, party: str = DEFAULT_PARTY, promo: str = DEFAULT_PROMO) -> str:
    """Filesystem-safe name. Colons are removed; the ``Z`` suffix stays.

    Non-default party and promo are appended, party first, so the original
    2a3c/none files keep the name they were given.
    """
    stamp = normalize_scraped_at(scraped_at).replace(":", "")
    suffix: list[str] = []
    if party != DEFAULT_PARTY:
        suffix.append(party)
    if promo != DEFAULT_PROMO:
        suffix.append(promo)
    extra = ("-" + "-".join(suffix)) if suffix else ""
    return f"{stamp}{extra}.csv.gz"


def append_document(history_dir: Path, document: dict) -> Path:
    """Append the rows of one party × promo results document."""
    scraped_at = document.get("generated_at")
    if not scraped_at:
        raise ValueError("results document has no generated_at")
    rows = document.get("results")
    if not isinstance(rows, list):
        raise ValueError("results document has no results list")
    return append_run(
        history_dir,
        rows,
        scraped_at=scraped_at,
        party=_dimension(document, "party", DEFAULT_PARTY),
        promo=_dimension(document, "promo", DEFAULT_PROMO),
    )


def append_run(
    history_dir: Path,
    rows: list[dict],
    *,
    scraped_at: datetime | str,
    party: str = DEFAULT_PARTY,
    promo: str = DEFAULT_PROMO,
) -> Path:
    """Write one new run file. Raises FileExistsError if that name is already stored."""
    stamp = normalize_scraped_at(scraped_at)
    runs = history_dir / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    path = runs / run_filename(stamp, party=party, promo=promo)
    payload = _encode(stamp, rows, party=party, promo=promo)
    try:
        with path.open("xb") as handle:
            handle.write(payload)
    except FileExistsError:
        raise FileExistsError(f"history run already exists: {path}") from None
    return path


def iter_rows(history_dir: Path):
    """Yield history rows from every run file, oldest filename first."""
    runs = history_dir / "runs"
    if not runs.is_dir():
        return
    for path in sorted(runs.glob("*.csv.gz")):
        yield from _read_gzip_csv(path)


def _encode(scraped_at: str, rows: list[dict], *, party: str, promo: str) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=HISTORY_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(_history_row(scraped_at, row, party=party, promo=promo))
    text = buffer.getvalue().encode("utf-8")
    out = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=out, mtime=0) as handle:
        handle.write(text)
    return out.getvalue()


def _history_row(scraped_at: str, row: dict, *, party: str, promo: str) -> dict[str, str]:
    return {
        "scraped_at": scraped_at,
        "check_in": str(row.get("check_in") or ""),
        "nights": _int_text(row.get("nights")),
        "rooms": _int_text(row.get("rooms")),
        "board": str(row.get("board") or ""),
        "status": str(row.get("status") or ""),
        "total_price": _money(row.get("total_price")),
        "price_per_night": _money(row.get("price_per_night")),
        "room_type": str(row.get("room_type") or ""),
        "party": str(row.get("party") or party or DEFAULT_PARTY),
        "promo": str(row.get("promo") or promo or DEFAULT_PROMO),
    }


def _dimension(document: dict, key: str, default: str) -> str:
    query = document.get("query") if isinstance(document.get("query"), dict) else {}
    value = document.get(key) or (query or {}).get(key)
    if not value:
        rows = document.get("results") or []
        if rows and isinstance(rows[0], dict):
            value = rows[0].get(key)
    return str(value or default)


def _int_text(value) -> str:
    if value is None or value == "":
        return ""
    return str(int(value))


def _money(value) -> str:
    if value is None or value == "":
        return ""
    return f"{float(value):.2f}"


def _read_gzip_csv(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        return [_normalize_history_row(row) for row in csv.DictReader(handle)]


def _normalize_history_row(row: dict[str, str]) -> dict[str, str]:
    """Fill party and promo when an older snapshot omitted the columns."""
    normalized = {field: (row.get(field) or "") for field in HISTORY_FIELDS}
    if not normalized["party"]:
        normalized["party"] = DEFAULT_PARTY
    if not normalized["promo"]:
        normalized["promo"] = DEFAULT_PROMO
    return normalized

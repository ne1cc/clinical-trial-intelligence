from datetime import UTC, date, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def utc_now_iso() -> str:
    return utc_now().isoformat(timespec="seconds")


def utc_now_compact() -> str:
    """Filesystem-safe UTC timestamp, e.g. 20260724T153000Z."""
    return utc_now().strftime("%Y%m%dT%H%M%SZ")


def parse_partial_date(value: str | None) -> date | None:
    """ClinicalTrials.gov dates may be partial: YYYY, YYYY-MM, or YYYY-MM-DD.
    Missing parts default to the first day/month. Returns None if unparseable."""
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(str(value), fmt).date()
        except ValueError:
            continue
    return None

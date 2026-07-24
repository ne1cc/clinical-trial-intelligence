"""Pagination over the studies endpoint: follow nextPageToken until absent."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from src.ingest.ctg_client import CTGClient


@dataclass(frozen=True)
class PageResult:
    page_number: int
    payload: dict[str, Any]
    raw_text: str
    page_token: str | None


def iter_pages(
    client: CTGClient,
    params: dict[str, str],
    max_pages: int | None = None,
) -> Iterator[PageResult]:
    token: str | None = None
    page_number = 1
    while True:
        payload, raw_text = client.fetch_page(params, page_token=token)
        yield PageResult(
            page_number=page_number, payload=payload, raw_text=raw_text, page_token=token
        )
        token = payload.get("nextPageToken")
        if not token:
            return
        if max_pages is not None and page_number >= max_pages:
            return
        page_number += 1

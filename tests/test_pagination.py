import httpx
import respx

from src.ingest.ctg_client import CTGClient
from src.ingest.pagination import iter_pages
from tests.test_ctg_client import STUDIES, make_api


def _two_page_responder(request: httpx.Request) -> httpx.Response:
    token = request.url.params.get("pageToken")
    if token is None:
        return httpx.Response(
            200,
            json={"studies": [{"id": 1}, {"id": 2}], "nextPageToken": "tok2", "totalCount": 3},
        )
    assert token == "tok2"
    return httpx.Response(200, json={"studies": [{"id": 3}]})


@respx.mock
def test_follows_next_page_token_until_absent():
    respx.get(STUDIES).mock(side_effect=_two_page_responder)
    with CTGClient(make_api()) as client:
        pages = list(iter_pages(client, client.build_params()))
    assert [p.page_number for p in pages] == [1, 2]
    assert pages[0].page_token is None
    assert pages[1].page_token == "tok2"
    assert pages[0].payload["nextPageToken"] == "tok2"
    assert "nextPageToken" not in pages[1].payload


@respx.mock
def test_max_pages_caps_iteration():
    route = respx.get(STUDIES).mock(side_effect=_two_page_responder)
    with CTGClient(make_api()) as client:
        pages = list(iter_pages(client, client.build_params(), max_pages=1))
    assert len(pages) == 1
    assert route.call_count == 1


@respx.mock
def test_single_page_stops_without_token():
    respx.get(STUDIES).mock(return_value=httpx.Response(200, json={"studies": []}))
    with CTGClient(make_api()) as client:
        pages = list(iter_pages(client, client.build_params()))
    assert len(pages) == 1

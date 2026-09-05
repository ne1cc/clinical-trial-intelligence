from src.ingest.ctg_client import CTGClient
from src.ingest.pagination import iter_pages
from tests.test_ctg_client import STUDIES, make_api


def _two_page_responder(request, context):
    token = request.qs.get("pagetoken")
    if token is None:
        return {"studies": [{"id": 1}, {"id": 2}], "nextPageToken": "tok2", "totalCount": 3}
    assert token == ["tok2"]
    return {"studies": [{"id": 3}]}


def test_follows_next_page_token_until_absent(requests_mock):
    requests_mock.get(STUDIES, json=_two_page_responder)
    with CTGClient(make_api()) as client:
        pages = list(iter_pages(client, client.build_params()))
    assert [p.page_number for p in pages] == [1, 2]
    assert pages[0].page_token is None
    assert pages[1].page_token == "tok2"
    assert pages[0].payload["nextPageToken"] == "tok2"
    assert "nextPageToken" not in pages[1].payload


def test_max_pages_caps_iteration(requests_mock):
    requests_mock.get(STUDIES, json=_two_page_responder)
    with CTGClient(make_api()) as client:
        pages = list(iter_pages(client, client.build_params(), max_pages=1))
    assert len(pages) == 1
    assert requests_mock.call_count == 1


def test_single_page_stops_without_token(requests_mock):
    requests_mock.get(STUDIES, json={"studies": []})
    with CTGClient(make_api()) as client:
        pages = list(iter_pages(client, client.build_params()))
    assert len(pages) == 1

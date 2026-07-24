import httpx
import pytest
import respx

from src.config import ApiConfig, HttpConfig
from src.ingest.ctg_client import CTGClient
from src.ingest.retry_policy import RetryableHTTPStatusError

BASE = "https://ctg.test/api/v2"
STUDIES = f"{BASE}/studies"


def make_api(**overrides) -> ApiConfig:
    defaults = dict(
        base_url=BASE,
        studies_endpoint="/studies",
        page_size=2,
        count_total=True,
        query_params={
            "query.cond": "Alzheimer Disease",
            "filter.advanced": "AREA[StudyType]INTERVENTIONAL",
            "filter.overallStatus": ["RECRUITING", "COMPLETED"],
        },
        http=HttpConfig(
            timeout_seconds=5,
            max_retries=3,
            backoff_initial_seconds=0.01,
            backoff_max_seconds=0.02,
        ),
    )
    defaults.update(overrides)
    return ApiConfig(**defaults)


def test_build_params_joins_list_filters_and_adds_paging():
    params = CTGClient(make_api()).build_params()
    assert params["filter.overallStatus"] == "RECRUITING|COMPLETED"
    assert params["query.cond"] == "Alzheimer Disease"
    assert params["filter.advanced"] == "AREA[StudyType]INTERVENTIONAL"
    assert params["pageSize"] == "2"
    assert params["format"] == "json"
    assert params["countTotal"] == "true"


def test_build_params_condition_override():
    params = CTGClient(make_api()).build_params(condition="Lewy Body Dementia")
    assert params["query.cond"] == "Lewy Body Dementia"


@respx.mock
def test_fetch_page_returns_payload_and_raw_text():
    respx.get(STUDIES).mock(return_value=httpx.Response(200, json={"studies": []}))
    with CTGClient(make_api()) as client:
        payload, raw_text = client.fetch_page(client.build_params())
    assert payload == {"studies": []}
    assert '"studies"' in raw_text


@respx.mock
def test_retries_on_503_then_succeeds():
    route = respx.get(STUDIES).mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(200, json={"studies": [{"protocolSection": {}}]}),
        ]
    )
    with CTGClient(make_api()) as client:
        payload, _ = client.fetch_page(client.build_params())
    assert route.call_count == 2
    assert len(payload["studies"]) == 1


@respx.mock
def test_no_retry_on_client_error_400():
    route = respx.get(STUDIES).mock(return_value=httpx.Response(400))
    with CTGClient(make_api()) as client:
        with pytest.raises(httpx.HTTPStatusError):
            client.fetch_page(client.build_params())
    assert route.call_count == 1


@respx.mock
def test_retries_exhausted_raises_retryable_error():
    route = respx.get(STUDIES).mock(return_value=httpx.Response(503))
    with CTGClient(make_api()) as client:
        with pytest.raises(RetryableHTTPStatusError):
            client.fetch_page(client.build_params())
    assert route.call_count == 3

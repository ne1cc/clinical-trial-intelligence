import pytest
import requests

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


def test_build_params_full_catalog_profile_has_no_filters():
    params = CTGClient(make_api(query_params={}, page_size=1000)).build_params()
    assert "query.cond" not in params
    assert "filter.overallStatus" not in params
    assert "filter.advanced" not in params
    assert params["pageSize"] == "1000"


def test_fetch_page_returns_payload_and_raw_text(requests_mock):
    requests_mock.get(STUDIES, json={"studies": []})
    with CTGClient(make_api()) as client:
        payload, raw_text = client.fetch_page(client.build_params())
    assert payload == {"studies": []}
    assert '"studies"' in raw_text


def test_retries_on_503_then_succeeds(requests_mock):
    requests_mock.get(
        STUDIES,
        [
            {"status_code": 503},
            {"json": {"studies": [{"protocolSection": {}}]}, "status_code": 200},
        ],
    )
    with CTGClient(make_api()) as client:
        payload, _ = client.fetch_page(client.build_params())
    assert requests_mock.call_count == 2
    assert len(payload["studies"]) == 1


def test_no_retry_on_client_error_400(requests_mock):
    requests_mock.get(STUDIES, status_code=400)
    with CTGClient(make_api()) as client:
        with pytest.raises(requests.HTTPError):
            client.fetch_page(client.build_params())
    assert requests_mock.call_count == 1


def test_retries_exhausted_raises_retryable_error(requests_mock):
    requests_mock.get(STUDIES, status_code=503)
    with CTGClient(make_api()) as client:
        with pytest.raises(RetryableHTTPStatusError):
            client.fetch_page(client.build_params())
    assert requests_mock.call_count == 3

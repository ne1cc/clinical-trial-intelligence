from src.config import get_config, load_config


def test_load_config():
    cfg = load_config()
    assert cfg.api.base_url
    assert cfg.paths.silver
    assert cfg.paths.duckdb
    assert get_config() is not None


def test_api_status_filter_matches_scope_statuses():
    cfg = load_config()
    api_statuses = cfg.api.query_params["filter.overallStatus"]
    assert sorted(api_statuses) == sorted(cfg.scope["statuses"])

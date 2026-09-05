from src.config import get_config, load_config


def test_load_config():
    cfg = load_config()
    assert cfg.api.base_url
    assert cfg.paths.silver
    assert cfg.paths.duckdb
    assert get_config() is not None


def test_load_full_catalog_config_is_isolated_from_default():
    cfg = load_config("config/full_catalog_config.yml")
    default = load_config()
    assert cfg.api.query_params == {}
    assert cfg.api.page_size == 1000
    assert cfg.paths.bronze_manifests != default.paths.bronze_manifests
    assert cfg.paths.bronze_api_responses != default.paths.bronze_api_responses


def test_api_status_filter_matches_scope_statuses():
    cfg = load_config()
    api_statuses = cfg.api.query_params["filter.overallStatus"]
    assert sorted(api_statuses) == sorted(cfg.scope["statuses"])

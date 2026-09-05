from src.cli import build_parser, main


def test_cli_parser_ingest():
    parser = build_parser()
    args = parser.parse_args(
        ["ingest", "--condition", "Alzheimer Disease", "--full-refresh", "--max-pages", "5"]
    )
    assert args.command == "ingest"
    assert args.condition == "Alzheimer Disease"
    assert args.full_refresh is True
    assert args.max_pages == 5


def test_cli_parser_ingest_profile_default():
    parser = build_parser()
    args = parser.parse_args(["ingest"])
    assert args.profile == "default"


def test_cli_parser_ingest_profile_full_catalog():
    parser = build_parser()
    args = parser.parse_args(["ingest", "--profile", "full-catalog"])
    assert args.profile == "full-catalog"


def test_cli_main_ingest_full_catalog_passes_full_catalog_config(monkeypatch):
    captured = {}

    class FakeManifest:
        status = "success"

    def fake_run_ingestion(**kwargs):
        captured.update(kwargs)
        return FakeManifest()

    monkeypatch.setattr("src.ingest.extract_studies.run_ingestion", fake_run_ingestion)

    exit_code = main(["ingest", "--profile", "full-catalog"])

    assert exit_code == 0
    assert captured["profile"] == "full-catalog"
    assert captured["config"] is not None
    assert str(captured["config"].paths.bronze_manifests).endswith("bronze_full_catalog/manifests")


def test_cli_main_ingest_default_profile_passes_no_config_override(monkeypatch):
    captured = {}

    class FakeManifest:
        status = "success"

    def fake_run_ingestion(**kwargs):
        captured.update(kwargs)
        return FakeManifest()

    monkeypatch.setattr("src.ingest.extract_studies.run_ingestion", fake_run_ingestion)

    exit_code = main(["ingest"])

    assert exit_code == 0
    assert captured["profile"] == "default"
    assert captured["config"] is None


def test_cli_main_rejects_condition_with_full_catalog_profile(monkeypatch):
    entered = []

    class NoNetworkClient:
        def __init__(self, api):
            pass

        def __enter__(self):
            entered.append(True)
            raise RuntimeError("network guard: client should never be entered")

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("src.ingest.extract_studies.CTGClient", NoNetworkClient)

    exit_code = main(["ingest", "--profile", "full-catalog", "--condition", "Cancer"])

    assert exit_code == 1
    assert not entered


def test_cli_parser_transform():
    parser = build_parser()
    args = parser.parse_args(["transform", "--run-id", "2026-09-04", "--force"])
    assert args.command == "transform"
    assert args.run_id == "2026-09-04"
    assert args.force is True


def test_cli_parser_transform_profile_default():
    parser = build_parser()
    args = parser.parse_args(["transform"])
    assert args.profile == "default"


def test_cli_parser_transform_profile_full_catalog():
    parser = build_parser()
    args = parser.parse_args(["transform", "--profile", "full-catalog"])
    assert args.profile == "full-catalog"


def test_cli_main_transform_full_catalog_passes_config_to_transform_and_profile(monkeypatch):
    transform_calls = []
    profile_calls = []

    def fake_run_transform(**kwargs):
        transform_calls.append(kwargs)
        return ["r1"]

    def fake_profile_run(run_id, **kwargs):
        profile_calls.append({"run_id": run_id, **kwargs})
        return {}

    monkeypatch.setattr("src.transform.build_silver_entities.run_transform", fake_run_transform)
    monkeypatch.setattr("src.quality.profiling.profile_run", fake_profile_run)

    exit_code = main(["transform", "--profile", "full-catalog"])

    assert exit_code == 0
    assert len(transform_calls) == 1
    assert len(profile_calls) == 1
    for captured in (*transform_calls, *profile_calls):
        assert captured["config"] is not None
        assert str(captured["config"].paths.silver).endswith("silver_full_catalog")


def test_cli_main_transform_default_passes_no_config_override(monkeypatch):
    transform_calls = []
    profile_calls = []

    def fake_run_transform(**kwargs):
        transform_calls.append(kwargs)
        return ["r1"]

    def fake_profile_run(run_id, **kwargs):
        profile_calls.append({"run_id": run_id, **kwargs})
        return {}

    monkeypatch.setattr("src.transform.build_silver_entities.run_transform", fake_run_transform)
    monkeypatch.setattr("src.quality.profiling.profile_run", fake_profile_run)

    exit_code = main(["transform"])

    assert exit_code == 0
    assert transform_calls[0]["config"] is None
    assert profile_calls[0]["config"] is None


def test_cli_parser_quality_report():
    parser = build_parser()
    args = parser.parse_args(["quality-report", "--update-schema-baseline"])
    assert args.command == "quality-report"
    assert args.update_schema_baseline is True

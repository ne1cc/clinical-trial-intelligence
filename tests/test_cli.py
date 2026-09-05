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
    """--profile default is still the default and maps to adrd at runtime."""
    parser = build_parser()
    args = parser.parse_args(["ingest"])
    assert args.profile == "default"


def test_cli_parser_ingest_profile_full_catalog_legacy_alias():
    """Legacy full-catalog hyphen alias is accepted by the parser."""
    parser = build_parser()
    args = parser.parse_args(["ingest", "--profile", "full-catalog"])
    assert args.profile == "full-catalog"


def test_cli_parser_ingest_profile_full_catalog_underscore():
    """New canonical full_catalog underscore name is accepted."""
    parser = build_parser()
    args = parser.parse_args(["ingest", "--profile", "full_catalog"])
    assert args.profile == "full_catalog"


def test_cli_main_ingest_resolves_profile_via_registry(monkeypatch):
    """main() resolves --profile to an IndicationProfile via ProfileRegistry."""
    captured = {}

    class FakeManifest:
        status = "success"

    def fake_run_ingestion(**kwargs):
        captured.update(kwargs)
        return FakeManifest()

    class FakeProfile:
        profile_id = "adrd"
        ingest_only = False
        # duck-typed as IndicationProfile for hasattr check
        pass

    class FakeRegistry:
        def get(self, profile_id):
            assert profile_id == "adrd"
            return FakeProfile()

    monkeypatch.setattr("src.cli.get_registry", lambda: FakeRegistry())
    monkeypatch.setattr("src.ingest.extract_studies.run_ingestion", fake_run_ingestion)

    exit_code = main(["ingest"])

    assert exit_code == 0
    # config kwarg is now the IndicationProfile object (not None)
    assert captured.get("config") is not None


def test_cli_main_ingest_full_catalog_alias_resolves_to_full_catalog(monkeypatch):
    """--profile full-catalog (legacy alias) resolves to full_catalog profile."""
    resolved_ids = []

    class FakeManifest:
        status = "success"

    class FakeProfile:
        profile_id = "full_catalog"
        ingest_only = True
        pass

    class FakeRegistry:
        def get(self, profile_id):
            resolved_ids.append(profile_id)
            return FakeProfile()

    monkeypatch.setattr("src.cli.get_registry", lambda: FakeRegistry())
    monkeypatch.setattr(
        "src.ingest.extract_studies.run_ingestion",
        lambda **kw: FakeManifest(),
    )

    exit_code = main(["ingest", "--profile", "full-catalog"])

    assert exit_code == 0
    assert resolved_ids == ["full_catalog"]


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

    class FakeProfile:
        profile_id = "full_catalog"
        ingest_only = True
        pass

    class FakeRegistry:
        def get(self, profile_id):
            return FakeProfile()

    monkeypatch.setattr("src.cli.get_registry", lambda: FakeRegistry())
    monkeypatch.setattr("src.ingest.extract_studies.CTGClient", NoNetworkClient)

    exit_code = main(["ingest", "--profile", "full-catalog", "--condition", "Cancer"])

    assert exit_code == 1
    assert not entered


def test_cli_parser_orchestrate():
    parser = build_parser()
    args = parser.parse_args(["orchestrate"])
    assert args.command == "orchestrate"
    assert args.full_refresh is False
    assert args.max_pages is None


def test_cli_parser_orchestrate_full_refresh():
    parser = build_parser()
    args = parser.parse_args(["orchestrate", "--full-refresh", "--max-pages", "2"])
    assert args.full_refresh is True
    assert args.max_pages == 2


def test_cli_main_orchestrate_runs_all_profiles(monkeypatch):
    """orchestrate command invokes ingest + transform for each active profile."""
    ingested = []
    transformed = []

    class FakeManifest:
        status = "success"
        error = None

    class FakeProfileA:
        profile_id = "adrd"
        ingest_only = False

    class FakeProfileB:
        profile_id = "full_catalog"
        ingest_only = True  # should be ingested but NOT transformed

    class FakeRegistry:
        def active(self):
            return [FakeProfileA(), FakeProfileB()]

    def fake_ingest(**kwargs):
        ingested.append(kwargs["config"].profile_id)
        return FakeManifest()

    def fake_transform(**kwargs):
        transformed.append(kwargs.get("profile").profile_id if kwargs.get("profile") else "none")
        return []

    monkeypatch.setattr("src.cli.get_registry", lambda: FakeRegistry())
    monkeypatch.setattr("src.ingest.extract_studies.run_ingestion", fake_ingest)
    monkeypatch.setattr("src.transform.build_silver_entities.run_transform", fake_transform)
    monkeypatch.setattr("src.quality.profiling.profile_run", lambda run_id: None)

    exit_code = main(["orchestrate"])

    assert exit_code == 0
    assert set(ingested) == {"adrd", "full_catalog"}
    # ingest_only profile must NOT be transformed
    assert "full_catalog" not in transformed
    assert "adrd" in transformed


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

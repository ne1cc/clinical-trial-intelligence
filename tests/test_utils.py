from pathlib import Path

from src.utils.logging import setup_logging
from src.utils.paths import ensure_dir, project_root, resolve_path


def test_paths():
    root = project_root()
    assert (root / "pyproject.toml").exists()
    rel = resolve_path("config/project_config.yml")
    assert rel.is_absolute()
    abs_path = resolve_path(root / "config")
    assert abs_path == root / "config"


def test_ensure_dir(tmp_path: Path):
    sub = tmp_path / "nested" / "dir"
    created = ensure_dir(sub)
    assert created.exists()
    assert created.is_dir()


def test_setup_logging():
    log = setup_logging()
    assert log is not None

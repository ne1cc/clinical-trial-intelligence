import os
from pathlib import Path


def project_root() -> Path:
    """Repository root. CTI_PROJECT_ROOT overrides (absolute path); '.' means auto-detect."""
    env = os.getenv("CTI_PROJECT_ROOT")
    if env and env != ".":
        return Path(env).resolve()
    return Path(__file__).resolve().parents[2]


def resolve_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else project_root() / path


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path

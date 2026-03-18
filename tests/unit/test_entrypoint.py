"""Tests for CLI entry points defined in pyproject.toml."""

import tomllib
from pathlib import Path


def _load_pyproject() -> dict:
    pyproject_path = Path(__file__).parents[2] / "pyproject.toml"
    with open(pyproject_path, "rb") as f:
        return tomllib.load(f)


def test_gpstitch_dashboard_entry_point_exists():
    """Verify gpstitch-dashboard entry point is defined in pyproject.toml."""
    data = _load_pyproject()
    scripts = data["project"]["scripts"]
    assert "gpstitch-dashboard" in scripts
    assert scripts["gpstitch-dashboard"] == "gpstitch.scripts.gopro_dashboard_wrapper:main"


def test_gpstitch_entry_point_still_exists():
    """Verify the original gpstitch entry point is not broken."""
    data = _load_pyproject()
    scripts = data["project"]["scripts"]
    assert "gpstitch" in scripts
    assert scripts["gpstitch"] == "gpstitch.main:main"

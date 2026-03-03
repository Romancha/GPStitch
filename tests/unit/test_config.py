"""Tests for configuration module."""

import os


def test_default_settings():
    """Test default settings are loaded correctly."""
    # Import inside test to avoid side effects
    from gpstitch.config import Settings

    # Create settings with defaults
    settings = Settings()

    assert settings.host == "0.0.0.0"
    assert settings.port == 8000
    assert settings.local_mode is True
    assert ".gpstitch" in str(settings.templates_dir)


def test_mov_in_allowed_extensions():
    """Verify .mov is in allowed_extensions."""
    from gpstitch.config import Settings

    settings = Settings()

    assert ".mov" in settings.allowed_extensions


def test_env_prefix():
    """Test that environment variables use GPSTITCH_ prefix."""
    os.environ["GPSTITCH_PORT"] = "9000"

    try:
        from gpstitch.config import Settings

        settings = Settings()
        assert settings.port == 9000
    finally:
        del os.environ["GPSTITCH_PORT"]

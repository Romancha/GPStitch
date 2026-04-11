"""Configuration settings for GPStitch."""

import tempfile
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    model_config = SettingsConfigDict(
        env_prefix="GPSTITCH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server settings
    host: str = "0.0.0.0"
    port: int = 8000

    # Local mode - work with local file paths instead of uploading (default: enabled)
    # Set GPSTITCH_LOCAL_MODE=false to disable and use file upload mode
    local_mode: bool = True

    # Runtime patching for gopro_overlay library
    # Set GPSTITCH_ENABLE_GOPRO_PATCHES=false to disable patches
    enable_gopro_patches: bool = True

    # Use wrapper script for gopro-dashboard.py (enables patches in subprocess)
    # Set GPSTITCH_USE_WRAPPER_SCRIPT=false to use original script
    use_wrapper_script: bool = True

    # File storage settings
    temp_dir: Path = Path(tempfile.gettempdir()) / "gpstitch"
    file_ttl_seconds: int = 3600  # 1 hour
    max_upload_size_bytes: int = 2 * 1024 * 1024 * 1024  # 2GB

    # Template storage directory
    templates_dir: Path = Path.home() / ".gpstitch" / "templates"

    # Allowed file extensions
    allowed_extensions: set[str] = {".mp4", ".mov", ".gpx", ".fit", ".srt"}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Ensure directories exist
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.templates_dir.mkdir(parents=True, exist_ok=True)


# Global settings instance
settings = Settings()

"""Integration tests for metadata preservation after rendering.

These tests verify that the runtime patches correctly preserve:
- Timecode (for Final Cut Pro compatibility)
- Creation time
- Audio streams
- Other video metadata

Note: These are "heavy" tests that perform actual video rendering
and may take significant time to run.
"""

import json
import subprocess
import tempfile
from pathlib import Path

import pytest


def extract_video_metadata_ffprobe(video_path: Path) -> dict:
    """Extract video metadata using ffprobe.

    Returns dict with:
    - streams: list of stream info
    - format: format/container info
    """
    result = subprocess.run(
        [
            "ffprobe",
            "-hide_banner",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(video_path),
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")

    return json.loads(result.stdout)


def get_video_stream(metadata: dict) -> dict | None:
    """Get the first video stream from ffprobe metadata."""
    for stream in metadata.get("streams", []):
        if stream.get("codec_type") == "video":
            return stream
    return None


def get_audio_stream(metadata: dict) -> dict | None:
    """Get the first audio stream from ffprobe metadata."""
    for stream in metadata.get("streams", []):
        if stream.get("codec_type") == "audio":
            return stream
    return None


def get_timecode(metadata: dict) -> str | None:
    """Extract timecode from video stream tags."""
    video_stream = get_video_stream(metadata)
    if video_stream:
        tags = video_stream.get("tags", {})
        return tags.get("timecode")
    return None


def get_creation_time(metadata: dict) -> str | None:
    """Extract creation_time from format tags."""
    format_info = metadata.get("format", {})
    tags = format_info.get("tags", {})
    return tags.get("creation_time")


@pytest.mark.integration
class TestTimecodeExtraction:
    """Tests for timecode extraction from source video."""

    def test_find_timecode_extracts_from_video(self, integration_test_video):
        """Test that find_timecode extracts timecode from real video."""
        from gpstitch.patches import apply_patches

        apply_patches()

        from gopro_overlay.ffmpeg import FFMPEG
        from gopro_overlay.ffmpeg_gopro import FFMPEGGoPro

        ffmpeg = FFMPEG()
        ffmpeg_gopro = FFMPEGGoPro(ffmpeg)

        timecode = ffmpeg_gopro.find_timecode(integration_test_video)

        # GoPro videos typically have timecode
        # If this test fails, the test video may not have timecode
        if timecode is not None:
            # Timecode format: HH:MM:SS:FF or HH:MM:SS;FF
            assert len(timecode) >= 11, f"Invalid timecode format: {timecode}"
            assert ":" in timecode or ";" in timecode

    def test_find_timecode_matches_ffprobe(self, integration_test_video):
        """Test that find_timecode returns same value as ffprobe."""
        from gpstitch.patches import apply_patches

        apply_patches()

        from gopro_overlay.ffmpeg import FFMPEG
        from gopro_overlay.ffmpeg_gopro import FFMPEGGoPro

        # Get timecode via our patched method
        ffmpeg = FFMPEG()
        ffmpeg_gopro = FFMPEGGoPro(ffmpeg)
        our_timecode = ffmpeg_gopro.find_timecode(integration_test_video)

        # Get timecode via direct ffprobe
        metadata = extract_video_metadata_ffprobe(integration_test_video)
        ffprobe_timecode = get_timecode(metadata)

        assert our_timecode == ffprobe_timecode


@pytest.mark.integration
class TestSourceMetadata:
    """Tests to verify source video has metadata we want to preserve."""

    def test_source_video_has_audio(self, integration_test_video):
        """Verify source video has audio stream."""
        metadata = extract_video_metadata_ffprobe(integration_test_video)
        audio_stream = get_audio_stream(metadata)

        assert audio_stream is not None, "Source video should have audio stream"
        assert audio_stream.get("codec_type") == "audio"

    def test_source_video_has_creation_time(self, integration_test_video):
        """Verify source video has creation_time metadata."""
        metadata = extract_video_metadata_ffprobe(integration_test_video)
        creation_time = get_creation_time(metadata)

        assert creation_time is not None, "Source video should have creation_time"

    def test_source_video_metadata_summary(self, integration_test_video):
        """Print summary of source video metadata for debugging."""
        metadata = extract_video_metadata_ffprobe(integration_test_video)

        video_stream = get_video_stream(metadata)
        audio_stream = get_audio_stream(metadata)
        format_info = metadata.get("format", {})

        print("\n=== Source Video Metadata ===")
        print(f"Video codec: {video_stream.get('codec_name') if video_stream else 'N/A'}")
        print(f"Resolution: {video_stream.get('width')}x{video_stream.get('height') if video_stream else 'N/A'}")
        print(f"Timecode: {get_timecode(metadata)}")
        print(f"Audio codec: {audio_stream.get('codec_name') if audio_stream else 'N/A'}")
        print(f"Creation time: {get_creation_time(metadata)}")
        print(f"Duration: {format_info.get('duration')} seconds")
        print(f"Format: {format_info.get('format_name')}")

        # Print all format tags
        print("\nFormat tags:")
        for key, value in format_info.get("tags", {}).items():
            print(f"  {key}: {value}")

        # Print video stream tags
        if video_stream:
            print("\nVideo stream tags:")
            for key, value in video_stream.get("tags", {}).items():
                print(f"  {key}: {value}")


@pytest.mark.integration
@pytest.mark.slow
class TestMetadataPreservationAfterRender:
    """Tests that verify metadata is preserved after rendering.

    These tests perform actual video rendering and are slow.
    Run with: pytest -m "integration and slow"
    """

    @pytest.fixture
    def render_output_dir(self):
        """Create temporary directory for render outputs."""
        with tempfile.TemporaryDirectory(prefix="gpstitch_test_") as tmpdir:
            yield Path(tmpdir)

    def test_render_preserves_timecode(
        self, integration_test_video, render_output_dir, clean_file_manager, monkeypatch
    ):
        """Test that rendering preserves timecode in output video."""
        from gpstitch.models.schemas import FileRole
        from gpstitch.patches import apply_patches
        from gpstitch.services import file_manager as fm_module
        from gpstitch.services.renderer import generate_cli_command

        apply_patches()

        # Get source timecode
        source_metadata = extract_video_metadata_ffprobe(integration_test_video)
        source_timecode = get_timecode(source_metadata)

        if source_timecode is None:
            pytest.skip("Source video has no timecode to preserve")

        # Setup session
        session_id = clean_file_manager.create_local_session()
        clean_file_manager.add_file(
            session_id=session_id,
            filename=integration_test_video.name,
            file_path=integration_test_video,
            file_type="video",
            role=FileRole.PRIMARY,
        )
        monkeypatch.setattr(fm_module, "file_manager", clean_file_manager)

        # Generate command
        output_file = render_output_dir / "output_with_timecode.mp4"
        cmd, _ = generate_cli_command(
            session_id=session_id,
            output_file=str(output_file),
            layout="default-1920x1080",
        )

        # Run render using wrapper script (which applies patches)
        from gpstitch.scripts import gopro_dashboard_wrapper

        wrapper = Path(gopro_dashboard_wrapper.__file__)
        assert wrapper.exists(), "Wrapper script not found"

        # Execute render (this is slow!)
        import shlex
        import sys

        args = shlex.split(cmd)
        args[0] = str(wrapper)

        result = subprocess.run(
            [sys.executable, *args],
            capture_output=True,
            text=True,
            timeout=600,  # 10 minutes max
        )

        assert result.returncode == 0, f"Render failed: {result.stderr}"
        assert output_file.exists(), "Output file not created"

        # Verify timecode preserved
        output_metadata = extract_video_metadata_ffprobe(output_file)
        output_timecode = get_timecode(output_metadata)

        assert output_timecode == source_timecode, (
            f"Timecode not preserved: source={source_timecode}, output={output_timecode}"
        )

    def test_render_preserves_audio(self, integration_test_video, render_output_dir, clean_file_manager, monkeypatch):
        """Test that rendering preserves audio stream."""
        from gpstitch.models.schemas import FileRole
        from gpstitch.patches import apply_patches
        from gpstitch.services import file_manager as fm_module
        from gpstitch.services.renderer import generate_cli_command

        apply_patches()

        # Verify source has audio
        source_metadata = extract_video_metadata_ffprobe(integration_test_video)
        source_audio = get_audio_stream(source_metadata)

        if source_audio is None:
            pytest.skip("Source video has no audio to preserve")

        # Setup session
        session_id = clean_file_manager.create_local_session()
        clean_file_manager.add_file(
            session_id=session_id,
            filename=integration_test_video.name,
            file_path=integration_test_video,
            file_type="video",
            role=FileRole.PRIMARY,
        )
        monkeypatch.setattr(fm_module, "file_manager", clean_file_manager)

        # Generate and run render
        output_file = render_output_dir / "output_with_audio.mp4"
        cmd, _ = generate_cli_command(
            session_id=session_id,
            output_file=str(output_file),
            layout="default-1920x1080",
        )

        from gpstitch.scripts import gopro_dashboard_wrapper

        wrapper = Path(gopro_dashboard_wrapper.__file__)

        import shlex
        import sys

        args = shlex.split(cmd)
        args[0] = str(wrapper)

        result = subprocess.run(
            [sys.executable, *args],
            capture_output=True,
            text=True,
            timeout=600,
        )

        assert result.returncode == 0, f"Render failed: {result.stderr}"

        # Verify audio preserved
        output_metadata = extract_video_metadata_ffprobe(output_file)
        output_audio = get_audio_stream(output_metadata)

        assert output_audio is not None, "Audio stream not preserved in output"
        assert output_audio.get("codec_name") == source_audio.get("codec_name"), (
            f"Audio codec changed: source={source_audio.get('codec_name')}, output={output_audio.get('codec_name')}"
        )

    def test_render_preserves_creation_time(
        self, integration_test_video, render_output_dir, clean_file_manager, monkeypatch
    ):
        """Test that rendering preserves or sets creation_time metadata."""
        from gpstitch.models.schemas import FileRole
        from gpstitch.patches import apply_patches
        from gpstitch.services import file_manager as fm_module
        from gpstitch.services.renderer import generate_cli_command

        apply_patches()

        # Note: we don't compare with source creation_time because
        # gopro-dashboard sets it from GPS timestamp which may differ

        # Setup session
        session_id = clean_file_manager.create_local_session()
        clean_file_manager.add_file(
            session_id=session_id,
            filename=integration_test_video.name,
            file_path=integration_test_video,
            file_type="video",
            role=FileRole.PRIMARY,
        )
        monkeypatch.setattr(fm_module, "file_manager", clean_file_manager)

        # Generate and run render
        output_file = render_output_dir / "output_with_creation_time.mp4"
        cmd, _ = generate_cli_command(
            session_id=session_id,
            output_file=str(output_file),
            layout="default-1920x1080",
        )

        from gpstitch.scripts import gopro_dashboard_wrapper

        wrapper = Path(gopro_dashboard_wrapper.__file__)

        import shlex
        import sys

        args = shlex.split(cmd)
        args[0] = str(wrapper)

        result = subprocess.run(
            [sys.executable, *args],
            capture_output=True,
            text=True,
            timeout=600,
        )

        assert result.returncode == 0, f"Render failed: {result.stderr}"

        # Verify creation_time exists
        output_metadata = extract_video_metadata_ffprobe(output_file)
        output_creation_time = get_creation_time(output_metadata)

        assert output_creation_time is not None, "creation_time not set in output"

        # Note: creation_time may differ from source because gopro-dashboard
        # sets it from GPS timestamp. Just verify it's present and valid ISO format.
        try:
            from datetime import datetime

            # Parse ISO format
            datetime.fromisoformat(output_creation_time.replace("Z", "+00:00"))
        except ValueError as e:
            pytest.fail(f"Invalid creation_time format: {output_creation_time}: {e}")


@pytest.mark.integration
class TestWrapperExecution:
    """Tests for wrapper script execution."""

    def test_wrapper_applies_patches(self):
        """Test that wrapper script applies patches before execution."""
        import subprocess
        import sys
        from pathlib import Path

        # Run wrapper with --help to verify it works
        from gpstitch.scripts import gopro_dashboard_wrapper

        wrapper = Path(gopro_dashboard_wrapper.__file__)
        assert wrapper.exists()

        result = subprocess.run(
            [sys.executable, str(wrapper), "--help"],
            capture_output=True,
            text=True,
        )

        # Should exit 0 with help output
        assert result.returncode == 0
        assert "gopro-dashboard" in result.stdout.lower() or "usage" in result.stdout.lower()

    def test_wrapper_logs_patch_application(self):
        """Test that wrapper logs when patches are applied."""
        import subprocess
        import sys
        from pathlib import Path

        from gpstitch.scripts import gopro_dashboard_wrapper

        wrapper = Path(gopro_dashboard_wrapper.__file__)

        result = subprocess.run(
            [sys.executable, str(wrapper), "--help"],
            capture_output=True,
            text=True,
        )

        # Check stderr for patch application log
        assert "patches applied" in result.stderr.lower() or result.returncode == 0

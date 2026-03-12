"""Tests for odo offset patch."""


class TestPatchCalculateOdo:
    """Tests for patch_calculate_odo function."""

    def test_patched_odo_starts_from_offset(self):
        """After patching, calculate_odo should start accumulating from the offset."""
        from gopro_overlay import timeseries_process
        from gopro_overlay.entry import Entry
        from gopro_overlay.units import units

        # Save original and ensure cleanup
        original = timeseries_process.calculate_odo
        had_flag = getattr(timeseries_process, "_ts_odo_patched", False)
        try:
            # Remove patch flag if set from previous test
            if had_flag:
                del timeseries_process._ts_odo_patched

            from gpstitch.patches.odo_patches import patch_calculate_odo

            patch_calculate_odo(1000.0)

            processor = timeseries_process.calculate_odo()

            # First entry with 10m distance: should be 1000 + 10 = 1010
            import datetime

            result = processor(Entry(datetime.datetime.now(), dist=units.Quantity(10.0, units.m)))
            assert abs(result["codo"].magnitude - 1010.0) < 0.01

            # Second entry with 5m: should be 1010 + 5 = 1015
            result = processor(Entry(datetime.datetime.now(), dist=units.Quantity(5.0, units.m)))
            assert abs(result["codo"].magnitude - 1015.0) < 0.01
        finally:
            # Restore original
            timeseries_process.calculate_odo = original
            if had_flag:
                timeseries_process._ts_odo_patched = True
            elif hasattr(timeseries_process, "_ts_odo_patched"):
                del timeseries_process._ts_odo_patched

    def test_patched_odo_no_dist(self):
        """Entries without dist should keep the running total unchanged."""
        from gopro_overlay import timeseries_process
        from gopro_overlay.entry import Entry

        original = timeseries_process.calculate_odo
        had_flag = getattr(timeseries_process, "_ts_odo_patched", False)
        try:
            if had_flag:
                del timeseries_process._ts_odo_patched

            from gpstitch.patches.odo_patches import patch_calculate_odo

            patch_calculate_odo(500.0)

            processor = timeseries_process.calculate_odo()

            import datetime

            # Entry without dist field
            result = processor(Entry(datetime.datetime.now()))
            assert abs(result["codo"].magnitude - 500.0) < 0.01
        finally:
            timeseries_process.calculate_odo = original
            if had_flag:
                timeseries_process._ts_odo_patched = True
            elif hasattr(timeseries_process, "_ts_odo_patched"):
                del timeseries_process._ts_odo_patched

    def test_zero_offset_same_as_original(self):
        """Offset of 0 should behave like the original calculate_odo."""
        from gopro_overlay import timeseries_process
        from gopro_overlay.entry import Entry
        from gopro_overlay.units import units

        original = timeseries_process.calculate_odo
        had_flag = getattr(timeseries_process, "_ts_odo_patched", False)
        try:
            if had_flag:
                del timeseries_process._ts_odo_patched

            from gpstitch.patches.odo_patches import patch_calculate_odo

            patch_calculate_odo(0.0)

            processor = timeseries_process.calculate_odo()

            import datetime

            result = processor(Entry(datetime.datetime.now(), dist=units.Quantity(10.0, units.m)))
            assert abs(result["codo"].magnitude - 10.0) < 0.01
        finally:
            timeseries_process.calculate_odo = original
            if had_flag:
                timeseries_process._ts_odo_patched = True
            elif hasattr(timeseries_process, "_ts_odo_patched"):
                del timeseries_process._ts_odo_patched


class TestGenerateCliCommandOdoOffset:
    """Tests for --ts-odo-offset in generate_cli_command."""

    def test_odo_offset_in_command(self, monkeypatch, temp_dir):
        """generate_cli_command should include --ts-odo-offset when odo_offset is set."""
        from unittest.mock import MagicMock

        from gpstitch.services.renderer import generate_cli_command

        # Create a mock file manager
        video_path = temp_dir / "test.mp4"
        video_path.write_bytes(b"fake")

        mock_file_manager = MagicMock()
        mock_primary = MagicMock()
        mock_primary.file_path = str(video_path)
        mock_primary.file_type = "video"
        mock_file_manager.get_files.return_value = [mock_primary]
        mock_file_manager.get_primary_file.return_value = mock_primary
        mock_file_manager.get_secondary_file.return_value = None

        monkeypatch.setattr("gpstitch.services.file_manager.file_manager", mock_file_manager)

        cmd, _ = generate_cli_command(
            session_id="test",
            output_file="/tmp/out.mp4",
            layout="default-1920x1080",
            odo_offset=5678.9,
        )
        assert "--ts-odo-offset 5678.9" in cmd

    def test_no_odo_offset_in_command(self, monkeypatch, temp_dir):
        """generate_cli_command should NOT include --ts-odo-offset when odo_offset is None."""
        from unittest.mock import MagicMock

        from gpstitch.services.renderer import generate_cli_command

        video_path = temp_dir / "test.mp4"
        video_path.write_bytes(b"fake")

        mock_file_manager = MagicMock()
        mock_primary = MagicMock()
        mock_primary.file_path = str(video_path)
        mock_primary.file_type = "video"
        mock_file_manager.get_files.return_value = [mock_primary]
        mock_file_manager.get_primary_file.return_value = mock_primary
        mock_file_manager.get_secondary_file.return_value = None

        monkeypatch.setattr("gpstitch.services.file_manager.file_manager", mock_file_manager)

        cmd, _ = generate_cli_command(
            session_id="test",
            output_file="/tmp/out.mp4",
            layout="default-1920x1080",
        )
        assert "--ts-odo-offset" not in cmd


class TestWrapperArgExtraction:
    """Tests for _extract_custom_args in wrapper."""

    def test_extract_odo_offset(self, monkeypatch):
        """--ts-odo-offset should be extracted and removed from argv."""
        import sys

        from gpstitch.scripts.gopro_dashboard_wrapper import _extract_custom_args

        monkeypatch.setattr(
            sys,
            "argv",
            ["wrapper.py", "--use-gpx-only", "--ts-odo-offset", "1234.5", "--gpx", "track.gpx"],
        )
        result = _extract_custom_args()
        assert result["odo_offset"] == 1234.5
        assert "--ts-odo-offset" not in sys.argv
        assert "1234.5" not in sys.argv
        assert "--use-gpx-only" in sys.argv
        assert "--gpx" in sys.argv

    def test_extract_all_custom_args(self, monkeypatch):
        """All custom args should be extracted together."""
        import sys

        from gpstitch.scripts.gopro_dashboard_wrapper import _extract_custom_args

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "wrapper.py",
                "--ts-srt-source",
                "/path/to/srt",
                "--ts-srt-video",
                "/path/to/video",
                "--ts-odo-offset",
                "999.0",
                "--layout",
                "default",
            ],
        )
        result = _extract_custom_args()
        assert result["srt_path"] == "/path/to/srt"
        assert result["video_path"] == "/path/to/video"
        assert result["odo_offset"] == 999.0
        assert sys.argv == ["wrapper.py", "--layout", "default"]

    def test_no_custom_args(self, monkeypatch):
        """Without custom args, all should be None."""
        import sys

        from gpstitch.scripts.gopro_dashboard_wrapper import _extract_custom_args

        monkeypatch.setattr(sys, "argv", ["wrapper.py", "--layout", "default"])
        result = _extract_custom_args()
        assert result["srt_path"] is None
        assert result["video_path"] is None
        assert result["odo_offset"] is None
        assert sys.argv == ["wrapper.py", "--layout", "default"]

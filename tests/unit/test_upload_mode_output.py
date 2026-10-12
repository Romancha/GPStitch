"""Unit tests for upload mode: mtime preservation, persistent render output, download."""

import os

from gpstitch.api.upload import _restore_mtime


class TestRestoreMtime:
    """Uploaded copies must keep the original mtime - DJI SRT time alignment relies on it."""

    def test_applies_browser_last_modified(self, tmp_path):
        path = tmp_path / "DJI_0001.MP4"
        path.write_bytes(b"video")
        recorded_at_ms = 1_791_639_812_000  # 2026-10-10T13:43:32Z

        _restore_mtime(path, recorded_at_ms)

        assert os.stat(path).st_mtime == recorded_at_ms / 1000

    def test_missing_value_keeps_current_mtime(self, tmp_path):
        path = tmp_path / "DJI_0001.MP4"
        path.write_bytes(b"video")
        before = os.stat(path).st_mtime

        _restore_mtime(path, None)

        assert os.stat(path).st_mtime == before

    def test_invalid_value_does_not_raise(self, tmp_path):
        path = tmp_path / "DJI_0001.MP4"
        path.write_bytes(b"video")

        _restore_mtime(path, 10**30)

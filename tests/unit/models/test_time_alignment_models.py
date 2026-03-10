"""Tests for time alignment fields in Pydantic models."""

import pytest
from pydantic import ValidationError

from gpstitch.models.editor import EditorPreviewRequest
from gpstitch.models.schemas import GpxFitOptions, PreviewRequest


class TestPreviewRequestAlignment:
    """Test PreviewRequest video_time_alignment and time_offset_seconds."""

    def test_default_alignment_is_auto(self):
        req = PreviewRequest(session_id="s1")
        assert req.video_time_alignment == "auto"

    def test_default_offset_is_zero(self):
        req = PreviewRequest(session_id="s1")
        assert req.time_offset_seconds == 0

    def test_valid_auto(self):
        req = PreviewRequest(session_id="s1", video_time_alignment="auto")
        assert req.video_time_alignment == "auto"

    def test_valid_gpx_timestamps(self):
        req = PreviewRequest(session_id="s1", video_time_alignment="gpx-timestamps")
        assert req.video_time_alignment == "gpx-timestamps"

    def test_valid_manual(self):
        req = PreviewRequest(session_id="s1", video_time_alignment="manual")
        assert req.video_time_alignment == "manual"

    def test_offset_with_manual(self):
        req = PreviewRequest(session_id="s1", video_time_alignment="manual", time_offset_seconds=30)
        assert req.time_offset_seconds == 30

    def test_negative_offset(self):
        req = PreviewRequest(session_id="s1", video_time_alignment="manual", time_offset_seconds=-60)
        assert req.time_offset_seconds == -60

    def test_old_file_created_rejected(self):
        with pytest.raises(ValidationError):
            PreviewRequest(session_id="s1", video_time_alignment="file-created")

    def test_old_file_modified_rejected(self):
        with pytest.raises(ValidationError):
            PreviewRequest(session_id="s1", video_time_alignment="file-modified")

    def test_old_file_accessed_rejected(self):
        with pytest.raises(ValidationError):
            PreviewRequest(session_id="s1", video_time_alignment="file-accessed")

    def test_invalid_value_rejected(self):
        with pytest.raises(ValidationError):
            PreviewRequest(session_id="s1", video_time_alignment="bogus")


class TestGpxFitOptionsAlignment:
    """Test GpxFitOptions video_time_alignment and time_offset_seconds."""

    def test_default_alignment_is_auto(self):
        opts = GpxFitOptions()
        assert opts.video_time_alignment == "auto"

    def test_default_offset_is_zero(self):
        opts = GpxFitOptions()
        assert opts.time_offset_seconds == 0

    def test_valid_values_accepted(self):
        for val in ("auto", "gpx-timestamps", "manual"):
            opts = GpxFitOptions(video_time_alignment=val)
            assert opts.video_time_alignment == val

    def test_old_values_rejected(self):
        for val in ("file-created", "file-modified", "file-accessed"):
            with pytest.raises(ValidationError):
                GpxFitOptions(video_time_alignment=val)

    def test_offset_stored(self):
        opts = GpxFitOptions(video_time_alignment="manual", time_offset_seconds=120)
        assert opts.time_offset_seconds == 120


class TestEditorPreviewRequestAlignment:
    """Test EditorPreviewRequest video_time_alignment and time_offset_seconds."""

    def test_default_alignment_is_auto(self):
        req = EditorPreviewRequest(session_id="s1", layout={})
        assert req.video_time_alignment == "auto"

    def test_default_offset_is_zero(self):
        req = EditorPreviewRequest(session_id="s1", layout={})
        assert req.time_offset_seconds == 0

    def test_valid_values_accepted(self):
        for val in ("auto", "gpx-timestamps", "manual"):
            req = EditorPreviewRequest(session_id="s1", layout={}, video_time_alignment=val)
            assert req.video_time_alignment == val

    def test_old_values_rejected(self):
        for val in ("file-created", "file-modified", "file-accessed"):
            with pytest.raises(ValidationError):
                EditorPreviewRequest(session_id="s1", layout={}, video_time_alignment=val)

    def test_offset_with_manual(self):
        req = EditorPreviewRequest(session_id="s1", layout={}, video_time_alignment="manual", time_offset_seconds=-30)
        assert req.time_offset_seconds == -30

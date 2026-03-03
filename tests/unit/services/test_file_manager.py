"""Unit tests for FileManager service."""

import time

import pytest

from gpstitch.models.schemas import FileRole


class TestFileManagerSession:
    """Tests for session management."""

    def test_create_session_generates_uuid(self, clean_file_manager):
        """Session ID should be a valid UUID."""
        session_id = clean_file_manager.create_session()

        assert session_id
        assert len(session_id) == 36  # UUID format
        assert "-" in session_id

    def test_create_session_creates_directory(self, clean_file_manager):
        """Session directory should be created."""
        session_id = clean_file_manager.create_session()
        session_dir = clean_file_manager.base_dir / session_id

        assert session_dir.exists()
        assert session_dir.is_dir()

    def test_create_session_cleans_previous(self, clean_file_manager):
        """Creating new session should cleanup previous."""
        session1 = clean_file_manager.create_session()
        session1_dir = clean_file_manager.base_dir / session1

        session2 = clean_file_manager.create_session()

        assert not session1_dir.exists()
        assert clean_file_manager.session_exists(session2)

    def test_create_local_session_uses_prefix(self, clean_file_manager):
        """Local session ID should have 'local:' prefix."""
        session_id = clean_file_manager.create_local_session()

        assert session_id.startswith("local:")
        assert clean_file_manager.is_local_session(session_id)

    def test_local_session_no_directory_created(self, clean_file_manager):
        """Local session should not create directory on disk."""
        clean_file_manager.create_local_session()

        # No directory should be created for local sessions
        dirs = list(clean_file_manager.base_dir.iterdir())
        assert all(not d.name.startswith("local:") for d in dirs)

    def test_session_exists(self, clean_file_manager):
        """session_exists should return correct status."""
        session_id = clean_file_manager.create_session()

        assert clean_file_manager.session_exists(session_id)
        assert not clean_file_manager.session_exists("nonexistent")

    def test_local_session_exists(self, clean_file_manager):
        """session_exists should work for local sessions."""
        session_id = clean_file_manager.create_local_session()

        assert clean_file_manager.session_exists(session_id)


class TestFileManagerFiles:
    """Tests for file management."""

    def test_add_primary_file(self, clean_file_manager, temp_dir, sample_video_metadata):
        """Add primary file to session."""
        session_id = clean_file_manager.create_session()
        test_file = temp_dir / "test.mp4"
        test_file.write_bytes(b"fake video")

        file_info = clean_file_manager.add_file(
            session_id=session_id,
            filename="test.mp4",
            file_path=test_file,
            file_type="video",
            role=FileRole.PRIMARY,
            video_metadata=sample_video_metadata,
        )

        assert file_info.role == FileRole.PRIMARY
        assert file_info.filename == "test.mp4"
        assert file_info.video_metadata is not None
        assert file_info.video_metadata.width == 1920

    def test_add_secondary_file(self, clean_file_manager, temp_dir, sample_video_metadata, sample_gpx_metadata):
        """Add secondary GPX file to session with video."""
        session_id = clean_file_manager.create_session()

        # Add primary video first
        video_file = temp_dir / "test.mp4"
        video_file.write_bytes(b"fake video")
        clean_file_manager.add_file(
            session_id=session_id,
            filename="test.mp4",
            file_path=video_file,
            file_type="video",
            role=FileRole.PRIMARY,
            video_metadata=sample_video_metadata,
        )

        # Add secondary GPX
        gpx_file = temp_dir / "track.gpx"
        gpx_file.write_text("<gpx></gpx>")
        file_info = clean_file_manager.add_file(
            session_id=session_id,
            filename="track.gpx",
            file_path=gpx_file,
            file_type="gpx",
            role=FileRole.SECONDARY,
            gpx_fit_metadata=sample_gpx_metadata,
        )

        assert file_info.role == FileRole.SECONDARY
        assert file_info.file_type == "gpx"

    def test_add_secondary_requires_video_primary(self, clean_file_manager, temp_dir, sample_gpx_metadata):
        """Secondary file requires video as primary."""
        session_id = clean_file_manager.create_session()

        # Add GPX as primary
        gpx_file = temp_dir / "track.gpx"
        gpx_file.write_text("<gpx></gpx>")
        clean_file_manager.add_file(
            session_id=session_id,
            filename="track.gpx",
            file_path=gpx_file,
            file_type="gpx",
            role=FileRole.PRIMARY,
            gpx_fit_metadata=sample_gpx_metadata,
        )

        # Try to add another GPX as secondary - should fail
        gpx_file2 = temp_dir / "track2.gpx"
        gpx_file2.write_text("<gpx></gpx>")
        with pytest.raises(ValueError, match="Can only add secondary GPX/FIT when primary is a video"):
            clean_file_manager.add_file(
                session_id=session_id,
                filename="track2.gpx",
                file_path=gpx_file2,
                file_type="gpx",
                role=FileRole.SECONDARY,
            )

    def test_add_secondary_must_be_gpx_fit_srt(self, clean_file_manager, temp_dir, sample_video_metadata):
        """Secondary file must be GPX, FIT, or SRT."""
        session_id = clean_file_manager.create_session()

        # Add primary video
        video_file = temp_dir / "test.mp4"
        video_file.write_bytes(b"fake video")
        clean_file_manager.add_file(
            session_id=session_id,
            filename="test.mp4",
            file_path=video_file,
            file_type="video",
            role=FileRole.PRIMARY,
            video_metadata=sample_video_metadata,
        )

        # Try to add another video as secondary
        video_file2 = temp_dir / "test2.mp4"
        video_file2.write_bytes(b"fake video 2")
        with pytest.raises(ValueError, match="Secondary file must be GPX, FIT, or SRT"):
            clean_file_manager.add_file(
                session_id=session_id,
                filename="test2.mp4",
                file_path=video_file2,
                file_type="video",
                role=FileRole.SECONDARY,
            )

    def test_duplicate_role_rejected(self, clean_file_manager, temp_dir, sample_video_metadata):
        """Cannot add two files with same role."""
        session_id = clean_file_manager.create_session()

        video_file = temp_dir / "test.mp4"
        video_file.write_bytes(b"fake video")
        clean_file_manager.add_file(
            session_id=session_id,
            filename="test.mp4",
            file_path=video_file,
            file_type="video",
            role=FileRole.PRIMARY,
            video_metadata=sample_video_metadata,
        )

        video_file2 = temp_dir / "test2.mp4"
        video_file2.write_bytes(b"fake video 2")
        with pytest.raises(ValueError, match="already has a primary file"):
            clean_file_manager.add_file(
                session_id=session_id,
                filename="test2.mp4",
                file_path=video_file2,
                file_type="video",
                role=FileRole.PRIMARY,
            )

    def test_get_files(self, clean_file_manager, temp_dir, sample_video_metadata):
        """Get all files in session."""
        session_id = clean_file_manager.create_session()
        video_file = temp_dir / "test.mp4"
        video_file.write_bytes(b"fake video")

        clean_file_manager.add_file(
            session_id=session_id,
            filename="test.mp4",
            file_path=video_file,
            file_type="video",
            role=FileRole.PRIMARY,
            video_metadata=sample_video_metadata,
        )

        files = clean_file_manager.get_files(session_id)

        assert len(files) == 1
        assert files[0].filename == "test.mp4"

    def test_get_primary_file(self, clean_file_manager, temp_dir):
        """Get primary file from session."""
        session_id = clean_file_manager.create_session()
        video_file = temp_dir / "test.mp4"
        video_file.write_bytes(b"fake video")

        clean_file_manager.add_file(
            session_id=session_id,
            filename="test.mp4",
            file_path=video_file,
            file_type="video",
            role=FileRole.PRIMARY,
        )

        primary = clean_file_manager.get_primary_file(session_id)

        assert primary is not None
        assert primary.role == FileRole.PRIMARY

    def test_get_secondary_file(self, clean_file_manager, temp_dir, sample_video_metadata):
        """Get secondary file from session."""
        session_id = clean_file_manager.create_session()

        # Add video
        video_file = temp_dir / "test.mp4"
        video_file.write_bytes(b"fake video")
        clean_file_manager.add_file(
            session_id=session_id,
            filename="test.mp4",
            file_path=video_file,
            file_type="video",
            role=FileRole.PRIMARY,
            video_metadata=sample_video_metadata,
        )

        # Add GPX
        gpx_file = temp_dir / "track.gpx"
        gpx_file.write_text("<gpx></gpx>")
        clean_file_manager.add_file(
            session_id=session_id,
            filename="track.gpx",
            file_path=gpx_file,
            file_type="gpx",
            role=FileRole.SECONDARY,
        )

        secondary = clean_file_manager.get_secondary_file(session_id)

        assert secondary is not None
        assert secondary.role == FileRole.SECONDARY
        assert secondary.file_type == "gpx"

    def test_remove_file_by_role(self, clean_file_manager, temp_dir):
        """Remove file by role."""
        session_id = clean_file_manager.create_local_session()
        gpx_file = temp_dir / "track.gpx"
        gpx_file.write_text("<gpx></gpx>")

        clean_file_manager.add_file(
            session_id=session_id,
            filename="track.gpx",
            file_path=gpx_file,
            file_type="gpx",
            role=FileRole.PRIMARY,
        )

        removed = clean_file_manager.remove_file_by_role(session_id, FileRole.PRIMARY)

        assert removed
        assert clean_file_manager.get_primary_file(session_id) is None

    def test_remove_nonexistent_file_returns_false(self, clean_file_manager):
        """Removing nonexistent file returns False."""
        session_id = clean_file_manager.create_session()

        removed = clean_file_manager.remove_file_by_role(session_id, FileRole.SECONDARY)

        assert not removed

    def test_save_file(self, clean_file_manager):
        """Save file to session directory."""
        session_id = clean_file_manager.create_session()
        content = b"test file content"

        saved_path = clean_file_manager.save_file(session_id, "test.txt", content)

        assert saved_path.exists()
        assert saved_path.read_bytes() == content

    def test_save_file_local_session_fails(self, clean_file_manager):
        """Cannot save file to local session."""
        session_id = clean_file_manager.create_local_session()

        with pytest.raises(ValueError, match="Cannot save files to local session"):
            clean_file_manager.save_file(session_id, "test.txt", b"content")


class TestFileManagerCleanup:
    """Tests for cleanup operations."""

    def test_cleanup_session(self, clean_file_manager, temp_dir):
        """Cleanup session removes directory."""
        session_id = clean_file_manager.create_session()
        session_dir = clean_file_manager.base_dir / session_id

        # Add a file
        video_file = temp_dir / "test.mp4"
        video_file.write_bytes(b"fake")
        clean_file_manager.add_file(
            session_id=session_id,
            filename="test.mp4",
            file_path=video_file,
            file_type="video",
            role=FileRole.PRIMARY,
        )

        clean_file_manager.cleanup_session(session_id)

        assert not session_dir.exists()
        assert not clean_file_manager.session_exists(session_id)

    def test_cleanup_local_session(self, clean_file_manager):
        """Cleanup local session removes from memory."""
        session_id = clean_file_manager.create_local_session()

        clean_file_manager.cleanup_session(session_id)

        assert not clean_file_manager.session_exists(session_id)

    def test_cleanup_expired(self, clean_file_manager, monkeypatch):
        """Cleanup expired sessions."""
        session_id = clean_file_manager.create_session()

        # Mock time to simulate expiration (TTL is 3600 seconds)
        original_time = time.time()
        monkeypatch.setattr(time, "time", lambda: original_time + 7200)

        cleaned = clean_file_manager.cleanup_expired()

        # At least one session should be cleaned (the one we created)
        assert cleaned >= 1
        assert not clean_file_manager.session_exists(session_id)

    def test_cleanup_expired_keeps_fresh(self, clean_file_manager):
        """Fresh sessions are not cleaned."""
        session_id = clean_file_manager.create_session()

        clean_file_manager.cleanup_expired()

        # Our session should still exist (it's fresh)
        assert clean_file_manager.session_exists(session_id)

    def test_get_all_session_ids(self, clean_file_manager):
        """Get all session IDs including local."""
        session1 = clean_file_manager.create_session()
        session2 = clean_file_manager.create_local_session(skip_cleanup=True)

        all_ids = clean_file_manager.get_all_session_ids()

        assert session1 in all_ids
        assert session2 in all_ids

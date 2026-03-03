"""File management service for temporary storage."""

import json
import shutil
import time
import uuid
from pathlib import Path

from gpstitch.config import settings
from gpstitch.models.schemas import (
    FileInfo,
    FileRole,
    GPSQualityReport,
    GpxFitMetadata,
    VideoMetadata,
)


class FileManager:
    """Manages temporary file storage for uploaded files with multi-file session support."""

    # Prefix for local mode session IDs
    LOCAL_SESSION_PREFIX = "local:"
    FILES_METADATA = ".files.json"

    def __init__(self):
        self.base_dir = settings.temp_dir
        self._current_session: str | None = None
        # Map of local session IDs to file info lists
        self._local_sessions: dict[str, list[FileInfo]] = {}

    def create_session(self) -> str:
        """Create a new session directory and cleanup any existing session."""
        # Clean up previous session if exists
        if self._current_session:
            self.cleanup_session(self._current_session)

        session_id = str(uuid.uuid4())
        session_dir = self.base_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        # Store session metadata
        metadata_file = session_dir / ".metadata"
        metadata_file.write_text(str(time.time()))

        # Initialize empty files list
        self._save_files_metadata(session_id, [])

        self._current_session = session_id
        return session_id

    def create_local_session(self, skip_cleanup: bool = False) -> str:
        """Create a local session (files referenced by path, not copied).

        Used in local_mode to avoid copying large video files.

        Args:
            skip_cleanup: If True, don't clean up previous session (for batch operations)
        """
        # Clean up previous session if exists (unless skipping for batch)
        if not skip_cleanup and self._current_session:
            self.cleanup_session(self._current_session)

        session_id = f"{self.LOCAL_SESSION_PREFIX}{uuid.uuid4()}"
        self._local_sessions[session_id] = []
        self._current_session = session_id
        return session_id

    def is_local_session(self, session_id: str) -> bool:
        """Check if session is a local file reference."""
        return session_id.startswith(self.LOCAL_SESSION_PREFIX)

    def add_file(
        self,
        session_id: str,
        filename: str,
        file_path: Path,
        file_type: str,
        role: FileRole,
        video_metadata: VideoMetadata | None = None,
        gpx_fit_metadata: GpxFitMetadata | None = None,
        gps_quality: GPSQualityReport | None = None,
    ) -> FileInfo:
        """Add a file to the session with specified role.

        For upload mode: file should already be saved to session directory.
        For local mode: file_path is the original path (not copied).
        """
        # Validate role constraints
        files = self.get_files(session_id)

        # Check for duplicate roles
        existing_roles = [f.role for f in files]
        if role in existing_roles:
            raise ValueError(f"Session already has a {role.value} file")

        # Secondary must be gpx/fit/srt
        if role == FileRole.SECONDARY and file_type not in ("gpx", "fit", "srt"):
            raise ValueError("Secondary file must be GPX, FIT, or SRT")

        # Can only add secondary if primary is video
        if role == FileRole.SECONDARY:
            primary = self.get_primary_file(session_id)
            if not primary or primary.file_type != "video":
                raise ValueError("Can only add secondary GPX/FIT when primary is a video")

        file_info = FileInfo(
            filename=filename,
            file_path=str(file_path),
            file_type=file_type,
            role=role,
            video_metadata=video_metadata,
            gpx_fit_metadata=gpx_fit_metadata,
            gps_quality=gps_quality,
        )

        files.append(file_info)
        self._save_files_metadata(session_id, files)

        return file_info

    def save_file(self, session_id: str, filename: str, content: bytes) -> Path:
        """Save uploaded file to session directory."""
        if self.is_local_session(session_id):
            raise ValueError("Cannot save files to local session")

        session_dir = self.base_dir / session_id
        if not session_dir.exists():
            raise ValueError(f"Session {session_id} does not exist")

        file_path = session_dir / filename
        file_path.write_bytes(content)
        return file_path

    def get_files(self, session_id: str) -> list[FileInfo]:
        """Get all files in a session."""
        if self.is_local_session(session_id):
            return self._local_sessions.get(session_id, [])

        return self._load_files_metadata(session_id)

    def get_file_by_role(self, session_id: str, role: FileRole) -> FileInfo | None:
        """Get file by role."""
        files = self.get_files(session_id)
        for f in files:
            if f.role == role:
                return f
        return None

    def get_primary_file(self, session_id: str) -> FileInfo | None:
        """Get primary file from session."""
        return self.get_file_by_role(session_id, FileRole.PRIMARY)

    def get_secondary_file(self, session_id: str) -> FileInfo | None:
        """Get secondary file from session."""
        return self.get_file_by_role(session_id, FileRole.SECONDARY)

    def promote_to_primary(
        self,
        session_id: str,
        filename: str,
        file_path: Path,
        file_type: str,
        video_metadata: VideoMetadata | None = None,
        gps_quality: GPSQualityReport | None = None,
    ) -> list[FileInfo]:
        """Promote a new video file to PRIMARY, demoting existing GPX/FIT PRIMARY to SECONDARY.

        Used when a video is uploaded into a session that already has GPX/FIT as primary.
        """
        files = self.get_files(session_id)
        existing_primary = None
        for f in files:
            if f.role == FileRole.PRIMARY:
                existing_primary = f
                break

        if not existing_primary:
            raise ValueError("No primary file to demote")

        if existing_primary.file_type not in ("gpx", "fit", "srt"):
            raise ValueError("Can only promote when existing primary is GPX/FIT/SRT")

        # Demote existing PRIMARY to SECONDARY
        existing_primary.role = FileRole.SECONDARY

        # Add new video as PRIMARY
        new_primary = FileInfo(
            filename=filename,
            file_path=str(file_path),
            file_type=file_type,
            role=FileRole.PRIMARY,
            video_metadata=video_metadata,
            gps_quality=gps_quality,
        )
        files.append(new_primary)

        self._save_files_metadata(session_id, files)
        return files

    def remove_file_by_role(self, session_id: str, role: FileRole) -> bool:
        """Remove a file by role from the session."""
        files = self.get_files(session_id)
        file_to_remove = None

        for f in files:
            if f.role == role:
                file_to_remove = f
                break

        if not file_to_remove:
            return False

        # Remove physical file if not local session
        if not self.is_local_session(session_id):
            file_path = Path(file_to_remove.file_path)
            if file_path.exists():
                file_path.unlink()

        # Update metadata
        files = [f for f in files if f.role != role]
        self._save_files_metadata(session_id, files)

        return True

    def get_file_path(self, session_id: str) -> Path | None:
        """Get the path to the primary file in a session.

        Backward compatible method - returns primary file path.
        """
        primary = self.get_primary_file(session_id)
        if primary:
            return Path(primary.file_path)
        return None

    def get_filename(self, session_id: str) -> str | None:
        """Get the filename of the primary file."""
        primary = self.get_primary_file(session_id)
        return primary.filename if primary else None

    def cleanup_session(self, session_id: str) -> None:
        """Remove a session and all its files."""
        # Handle local sessions - just remove from dict
        if self.is_local_session(session_id):
            self._local_sessions.pop(session_id, None)
            if self._current_session == session_id:
                self._current_session = None
            return

        session_dir = self.base_dir / session_id
        if session_dir.exists():
            shutil.rmtree(session_dir)

        if self._current_session == session_id:
            self._current_session = None

    # Directories in temp_dir that are NOT sessions (should not be cleaned)
    RESERVED_DIRS = {"jobs"}

    def cleanup_expired(self) -> int:
        """Remove sessions older than TTL. Returns count of cleaned sessions."""
        cleaned = 0
        current_time = time.time()

        if not self.base_dir.exists():
            return 0

        for session_dir in self.base_dir.iterdir():
            if not session_dir.is_dir():
                continue

            # Skip reserved directories (jobs, etc.)
            if session_dir.name in self.RESERVED_DIRS:
                continue

            metadata_file = session_dir / ".metadata"
            if metadata_file.exists():
                try:
                    created_time = float(metadata_file.read_text())
                    if current_time - created_time > settings.file_ttl_seconds:
                        shutil.rmtree(session_dir)
                        cleaned += 1
                except (ValueError, OSError):
                    # Invalid metadata, clean up
                    shutil.rmtree(session_dir)
                    cleaned += 1
            else:
                # No metadata, clean up
                shutil.rmtree(session_dir)
                cleaned += 1

        return cleaned

    def session_exists(self, session_id: str) -> bool:
        """Check if a session exists."""
        # Handle local sessions
        if self.is_local_session(session_id):
            return session_id in self._local_sessions

        return (self.base_dir / session_id).exists()

    def get_all_session_ids(self) -> set:
        """Get all valid session IDs (both local and disk-based)."""
        session_ids = set(self._local_sessions.keys())

        if self.base_dir.exists():
            for session_dir in self.base_dir.iterdir():
                if session_dir.is_dir() and session_dir.name not in self.RESERVED_DIRS:
                    session_ids.add(session_dir.name)

        return session_ids

    def _save_files_metadata(self, session_id: str, files: list[FileInfo]) -> None:
        """Save files metadata to session."""
        if self.is_local_session(session_id):
            self._local_sessions[session_id] = files
            return

        session_dir = self.base_dir / session_id
        if not session_dir.exists():
            return

        files_file = session_dir / self.FILES_METADATA
        files_data = [f.model_dump() for f in files]
        files_file.write_text(json.dumps(files_data, indent=2))

    def _load_files_metadata(self, session_id: str) -> list[FileInfo]:
        """Load files metadata from session."""
        if self.is_local_session(session_id):
            return self._local_sessions.get(session_id, [])

        session_dir = self.base_dir / session_id
        files_file = session_dir / self.FILES_METADATA

        if not files_file.exists():
            return []

        try:
            data = json.loads(files_file.read_text())
            return [FileInfo(**f) for f in data]
        except (json.JSONDecodeError, ValueError):
            return []


# Global file manager instance
file_manager = FileManager()

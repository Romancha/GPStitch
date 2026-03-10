"""Tests for time-sync analyze endpoint."""

import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gpstitch.api.time_sync import (
    _calculate_overlap,
    _haversine_distance,
)


class TestHaversineDistance:
    def test_same_point_returns_zero(self):
        assert _haversine_distance(0, 0, 0, 0) == 0.0

    def test_known_distance(self):
        # ~111km between 0,0 and 1,0 (1 degree latitude)
        dist = _haversine_distance(0, 0, 1, 0)
        assert 110000 < dist < 112000


class TestTimeSyncAnalyzeEndpoint:
    """Tests for POST /api/time-sync/analyze."""

    @pytest.fixture
    def mock_deps(self, monkeypatch):
        """Mock all external dependencies for the endpoint."""
        import gpstitch.api.time_sync as mod

        mocks = {
            "file_manager": MagicMock(),
            "extract_creation_time": MagicMock(return_value=None),
            "get_video_duration": MagicMock(return_value=60.0),
            "calculate_overlap": MagicMock(return_value=None),
        }
        monkeypatch.setattr(mod, "file_manager", mocks["file_manager"])
        monkeypatch.setattr(mod, "_extract_creation_time", mocks["extract_creation_time"])
        monkeypatch.setattr(mod, "_get_video_duration", mocks["get_video_duration"])
        monkeypatch.setattr(mod, "_calculate_overlap", mocks["calculate_overlap"])
        return mocks

    @pytest.fixture
    def video_file(self, temp_dir):
        video_path = temp_dir / "test.mp4"
        video_path.write_bytes(b"fake video")
        return video_path

    @pytest.fixture
    def gpx_file(self, temp_dir):
        gpx_path = temp_dir / "track.gpx"
        gpx_path.write_text(
            '<?xml version="1.0"?><gpx><trk><trkseg></trkseg></trk></gpx>',
            encoding="utf-8",
        )
        return gpx_path

    def _make_file_info(self, file_path, role="primary", file_type="video"):
        fi = MagicMock()
        fi.file_path = str(file_path)
        fi.role = role
        fi.file_type = file_type
        return fi

    async def test_no_primary_file_returns_404(self, async_client, mock_deps):
        mock_deps["file_manager"].get_file_by_role.return_value = None

        response = await async_client.post(
            "/api/time-sync/analyze",
            json={"session_id": "test-session"},
        )

        assert response.status_code == 404
        assert "No primary video" in response.json()["detail"]

    async def test_video_not_found_returns_404(self, async_client, mock_deps):
        fi = self._make_file_info("/nonexistent/video.mp4")
        mock_deps["file_manager"].get_file_by_role.return_value = fi

        response = await async_client.post(
            "/api/time-sync/analyze",
            json={"session_id": "test-session"},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    async def test_non_video_primary_returns_400(self, async_client, mock_deps):
        fi = self._make_file_info("/some/track.gpx", file_type="gpx")
        mock_deps["file_manager"].get_file_by_role.return_value = fi

        response = await async_client.post(
            "/api/time-sync/analyze",
            json={"session_id": "test-session"},
        )

        assert response.status_code == 400
        assert "must be a video" in response.json()["detail"].lower()

    async def test_with_creation_time(self, async_client, mock_deps, video_file):
        creation = datetime.datetime(2024, 8, 8, 17, 13, 0, tzinfo=datetime.UTC)
        mock_deps["extract_creation_time"].return_value = creation
        mock_deps["get_video_duration"].return_value = 120.5

        fi = self._make_file_info(video_file)
        mock_deps["file_manager"].get_file_by_role.return_value = fi

        response = await async_client.post(
            "/api/time-sync/analyze",
            json={"session_id": "test-session"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "media-created"
        assert data["video_duration_sec"] == 120.5
        assert "2024-08-08T17:13:00" in data["video_start"]
        assert data["overlap"] is None

    async def test_fallback_to_file_stat(self, async_client, mock_deps, video_file):
        mock_deps["extract_creation_time"].return_value = None
        mock_deps["get_video_duration"].return_value = 60.0

        fi = self._make_file_info(video_file)
        mock_deps["file_manager"].get_file_by_role.return_value = fi

        response = await async_client.post(
            "/api/time-sync/analyze",
            json={"session_id": "test-session"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "file-created"
        assert data["video_duration_sec"] == 60.0

    async def test_with_offset_applied(self, async_client, mock_deps, video_file):
        creation = datetime.datetime(2024, 8, 8, 17, 0, 0, tzinfo=datetime.UTC)
        mock_deps["extract_creation_time"].return_value = creation
        mock_deps["get_video_duration"].return_value = 60.0

        fi = self._make_file_info(video_file)
        mock_deps["file_manager"].get_file_by_role.return_value = fi

        response = await async_client.post(
            "/api/time-sync/analyze",
            json={"session_id": "test-session", "time_offset_seconds": 300},
        )

        assert response.status_code == 200
        data = response.json()
        # 17:00 + 300s = 17:05
        assert "2024-08-08T17:05:00" in data["video_start"]

    async def test_with_gpx_overlap(self, async_client, mock_deps, video_file, gpx_file):
        creation = datetime.datetime(2024, 8, 8, 17, 0, 0, tzinfo=datetime.UTC)
        mock_deps["extract_creation_time"].return_value = creation
        mock_deps["get_video_duration"].return_value = 120.0

        from gpstitch.api.time_sync import OverlapInfo
        from gpstitch.models.schemas import FileRole

        mock_deps["calculate_overlap"].return_value = OverlapInfo(points=4, distance_m=150.3, avg_speed_kph=0.2)

        primary_fi = self._make_file_info(video_file)
        secondary_fi = self._make_file_info(gpx_file, role="secondary")

        def side_effect(session_id, role):
            if role == FileRole.PRIMARY:
                return primary_fi
            if role == FileRole.SECONDARY:
                return secondary_fi
            return None

        mock_deps["file_manager"].get_file_by_role.side_effect = side_effect

        response = await async_client.post(
            "/api/time-sync/analyze",
            json={"session_id": "test-session"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["overlap"] is not None
        assert data["overlap"]["points"] == 4
        assert data["overlap"]["distance_m"] == 150.3
        assert data["overlap"]["avg_speed_kph"] == 0.2

    async def test_no_overlap_case(self, async_client, mock_deps, video_file, gpx_file):
        creation = datetime.datetime(2024, 8, 8, 17, 0, 0, tzinfo=datetime.UTC)
        mock_deps["extract_creation_time"].return_value = creation
        mock_deps["get_video_duration"].return_value = 60.0
        mock_deps["calculate_overlap"].return_value = None

        from gpstitch.models.schemas import FileRole

        primary_fi = self._make_file_info(video_file)
        secondary_fi = self._make_file_info(gpx_file, role="secondary")

        def side_effect(session_id, role):
            if role == FileRole.PRIMARY:
                return primary_fi
            if role == FileRole.SECONDARY:
                return secondary_fi
            return None

        mock_deps["file_manager"].get_file_by_role.side_effect = side_effect

        response = await async_client.post(
            "/api/time-sync/analyze",
            json={"session_id": "test-session"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["overlap"] is None

    async def test_negative_offset(self, async_client, mock_deps, video_file):
        creation = datetime.datetime(2024, 8, 8, 17, 0, 0, tzinfo=datetime.UTC)
        mock_deps["extract_creation_time"].return_value = creation
        mock_deps["get_video_duration"].return_value = 60.0

        fi = self._make_file_info(video_file)
        mock_deps["file_manager"].get_file_by_role.return_value = fi

        response = await async_client.post(
            "/api/time-sync/analyze",
            json={"session_id": "test-session", "time_offset_seconds": -60},
        )

        assert response.status_code == 200
        data = response.json()
        # 17:00 - 60s = 16:59
        assert "2024-08-08T16:59:00" in data["video_start"]


class TestCalculateOverlap:
    """Unit tests for _calculate_overlap function."""

    def test_returns_none_when_no_entries(self):
        with patch("gopro_overlay.loading.load_external") as mock_load:
            mock_ts = MagicMock()
            mock_ts.items.return_value = []
            mock_load.return_value = mock_ts

            result = _calculate_overlap(
                datetime.datetime(2024, 1, 1, tzinfo=datetime.UTC),
                60.0,
                Path("/fake.gpx"),
            )
            assert result is None

    def test_returns_none_when_no_time_overlap(self):
        with patch("gopro_overlay.loading.load_external") as mock_load:
            entry1 = MagicMock()
            entry1.dt = datetime.datetime(2024, 1, 1, 10, 0, 0, tzinfo=datetime.UTC)
            entry1.point = MagicMock(lat=0.0, lon=0.0)
            entry2 = MagicMock()
            entry2.dt = datetime.datetime(2024, 1, 1, 10, 1, 0, tzinfo=datetime.UTC)
            entry2.point = MagicMock(lat=0.0, lon=0.0)

            mock_ts = MagicMock()
            mock_ts.items.return_value = [entry1, entry2]
            mock_load.return_value = mock_ts

            # Video starts at 12:00, GPX data at 10:00 — no overlap
            result = _calculate_overlap(
                datetime.datetime(2024, 1, 1, 12, 0, 0, tzinfo=datetime.UTC),
                60.0,
                Path("/fake.gpx"),
            )
            assert result is None

    def test_returns_overlap_info_when_overlap_exists(self):
        with patch("gopro_overlay.loading.load_external") as mock_load:
            base_time = datetime.datetime(2024, 1, 1, 10, 0, 0, tzinfo=datetime.UTC)
            entries = []
            for i in range(5):
                entry = MagicMock()
                entry.dt = base_time + datetime.timedelta(seconds=i * 10)
                entry.point = MagicMock(lat=48.0 + i * 0.001, lon=11.0 + i * 0.001)
                entries.append(entry)

            mock_ts = MagicMock()
            mock_ts.items.return_value = entries
            mock_load.return_value = mock_ts

            result = _calculate_overlap(base_time, 120.0, Path("/fake.gpx"))

            assert result is not None
            assert result.points == 5
            assert result.distance_m > 0
            assert result.avg_speed_kph > 0

"""Tests for the font picker endpoints and the font option on render requests."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from gpstitch.services.font_service import FontService


@pytest.fixture
def installed_font(sample_font, monkeypatch):
    """A font service that sees one installed font; returns the font file path."""
    monkeypatch.setattr("gpstitch.api.options.font_service", FontService([Path(sample_font).parent]))
    return sample_font


@pytest.fixture
async def session_id(async_client, api_test_video):
    response = await async_client.post("/api/local-file", json={"file_path": str(api_test_video)})
    return response.json()["session_id"]


class TestFontOptions:
    async def test_list_fonts(self, async_client, installed_font):
        response = await async_client.get("/api/options/fonts")

        assert response.status_code == 200
        fonts = response.json()["fonts"]
        assert len(fonts) == 1
        assert fonts[0]["path"] == installed_font
        assert fonts[0]["index"] == 0
        assert fonts[0]["family"] == "JetBrains Mono"
        assert fonts[0]["style"] == "Regular"
        assert fonts[0]["id"]

    async def test_font_preview_is_png(self, async_client, installed_font):
        font_id = (await async_client.get("/api/options/fonts")).json()["fonts"][0]["id"]

        response = await async_client.get(f"/api/options/fonts/{font_id}/preview.png")

        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert response.content.startswith(b"\x89PNG")

    async def test_unknown_font_preview_is_404(self, async_client, installed_font):
        response = await async_client.get("/api/options/fonts/0123456789abcdef/preview.png")

        assert response.status_code == 404

    async def test_uninstalled_font_preview_is_404(self, async_client, installed_font):
        font_id = (await async_client.get("/api/options/fonts")).json()["fonts"][0]["id"]
        Path(installed_font).unlink()

        response = await async_client.get(f"/api/options/fonts/{font_id}/preview.png")

        assert response.status_code == 404


class TestFontOnRenderRequests:
    async def test_render_start_stores_font(self, async_client, session_id, installed_font):
        with patch("gpstitch.api.render.render_service.start_render", new=AsyncMock()):
            response = await async_client.post(
                "/api/render/start",
                json={
                    "session_id": session_id,
                    "layout": "default-1920x1080",
                    "output_file": "/tmp/font_out.mp4",
                    "font": installed_font,
                    "font_index": 2,
                },
            )

        assert response.status_code == 200

        from gpstitch.services.job_manager import job_manager

        job = await job_manager.get_job(response.json()["job_id"])
        assert job.config.font == installed_font
        assert job.config.font_index == 2

    async def test_batch_stores_font(self, async_client, temp_dir, installed_font):
        video = temp_dir / "font_batch.mp4"
        video.write_bytes(b"fake video")

        response = await async_client.post(
            "/api/render/batch",
            json={"files": [{"video_path": str(video)}], "font": installed_font, "font_index": 1},
        )

        assert response.status_code == 200

        from gpstitch.services.job_manager import job_manager

        job = await job_manager.get_job(response.json()["job_ids"][0])
        assert job.config.font == installed_font
        assert job.config.font_index == 1

    async def test_command_includes_font(self, async_client, session_id, installed_font):
        response = await async_client.post(
            "/api/command",
            json={"session_id": session_id, "layout": "default-1920x1080", "font": installed_font},
        )

        assert response.status_code == 200
        assert f"--font {installed_font}" in response.json()["command"]

    async def test_negative_font_index_is_rejected(self, async_client, session_id):
        response = await async_client.post(
            "/api/command",
            json={"session_id": session_id, "layout": "default-1920x1080", "font": "/f.ttc", "font_index": -1},
        )

        assert response.status_code == 422

    async def test_preview_accepts_font(self, async_client, session_id, installed_font):
        with patch("gpstitch.api.preview.render_preview", return_value=(b"png", 1920, 1080)) as render_preview:
            response = await async_client.post(
                "/api/preview",
                json={"session_id": session_id, "font": installed_font, "font_index": 1},
            )

        assert response.status_code == 200
        assert render_preview.call_args.kwargs["font"] == installed_font
        assert render_preview.call_args.kwargs["font_index"] == 1

    async def test_editor_preview_accepts_font(self, async_client, session_id, installed_font, sample_editor_layout):
        preview = {"image_base64": "", "width": 1920, "height": 1080, "frame_time_ms": 0}
        with patch(
            "gpstitch.services.renderer.render_preview_from_layout", new=AsyncMock(return_value=preview)
        ) as render:
            response = await async_client.post(
                "/api/editor/preview",
                json={
                    "session_id": session_id,
                    "layout": sample_editor_layout.model_dump(mode="json"),
                    "font": installed_font,
                    "font_index": 1,
                },
            )

        assert response.status_code == 200
        assert render.call_args.kwargs["font"] == installed_font
        assert render.call_args.kwargs["font_index"] == 1

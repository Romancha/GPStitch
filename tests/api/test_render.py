"""API tests for render endpoints."""


class TestRenderJobs:
    """Tests for render job endpoints."""

    async def test_get_current_job_none(self, async_client):
        """GET /api/render/current when no job running."""
        response = await async_client.get("/api/render/current")

        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] is None


class TestCommandGeneration:
    """Tests for command generation endpoint."""

    async def test_generate_command(self, async_client, api_test_video):
        """POST /api/command generates CLI command."""
        # Create session
        upload_resp = await async_client.post("/api/local-file", json={"file_path": str(api_test_video)})
        session_id = upload_resp.json()["session_id"]

        # Generate command
        response = await async_client.post(
            "/api/command",
            json={
                "session_id": session_id,
                "layout": "default-1920x1080",
                "output_filename": "output.mp4",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "command" in data
        assert "input_file" in data
        assert "gpstitch-dashboard" in data["command"]
        assert str(api_test_video) in data["input_file"]

    async def test_generate_command_with_units(self, async_client, api_test_video):
        """POST /api/command with custom units."""
        # Create session
        upload_resp = await async_client.post("/api/local-file", json={"file_path": str(api_test_video)})
        session_id = upload_resp.json()["session_id"]

        # Generate command with units
        response = await async_client.post(
            "/api/command",
            json={
                "session_id": session_id,
                "layout": "default-1920x1080",
                "output_filename": "output.mp4",
                "units_speed": "mph",
                "units_altitude": "feet",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "mph" in data["command"]
        assert "feet" in data["command"]

    async def test_generate_command_invalid_session(self, async_client):
        """POST /api/command with invalid session returns 404."""
        response = await async_client.post(
            "/api/command",
            json={
                "session_id": "invalid-session",
                "layout": "default",
                "output_filename": "output.mp4",
            },
        )

        assert response.status_code == 404


class TestLayoutsAndOptions:
    """Tests for layouts and options endpoints."""

    async def test_get_layouts(self, async_client):
        """GET /api/layouts returns available layouts."""
        response = await async_client.get("/api/layouts")

        assert response.status_code == 200
        data = response.json()
        assert "layouts" in data
        assert len(data["layouts"]) > 0

    async def test_layouts_have_dimensions(self, async_client):
        """Layouts include dimensions."""
        response = await async_client.get("/api/layouts")
        data = response.json()

        for layout in data["layouts"]:
            assert "name" in layout
            assert "width" in layout
            assert "height" in layout
            assert layout["width"] > 0
            assert layout["height"] > 0

    async def test_get_unit_options(self, async_client):
        """GET /api/options/units returns unit options."""
        response = await async_client.get("/api/options/units")

        assert response.status_code == 200
        data = response.json()
        assert "categories" in data
        assert len(data["categories"]) > 0

    async def test_unit_options_have_categories(self, async_client):
        """Unit options have expected categories."""
        response = await async_client.get("/api/options/units")
        data = response.json()

        category_names = [c["name"] for c in data["categories"]]
        assert "speed" in category_names
        assert "altitude" in category_names

    async def test_get_map_styles(self, async_client):
        """GET /api/options/map-styles returns map styles."""
        response = await async_client.get("/api/options/map-styles")

        assert response.status_code == 200
        data = response.json()
        assert "styles" in data
        assert len(data["styles"]) > 0

    async def test_get_ffmpeg_profiles(self, async_client):
        """GET /api/options/ffmpeg-profiles returns profiles."""
        response = await async_client.get("/api/options/ffmpeg-profiles")

        assert response.status_code == 200
        data = response.json()
        assert "profiles" in data
        assert len(data["profiles"]) > 0

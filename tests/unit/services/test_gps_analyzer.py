"""Tests for GPS quality analyzer service."""

from telemetry_studio.models.schemas import GPSQualityReport
from telemetry_studio.services.gps_analyzer import (
    _build_report,
    _determine_quality_score,
    _generate_warnings,
)


class TestBuildReport:
    """Tests for _build_report function."""

    def test_empty_data_returns_no_signal(self):
        """Test that empty data returns no_signal quality."""
        report = _build_report(total_points=0, locked_points=0, dop_values=[])

        assert report.quality_score == "no_signal"
        assert report.total_points == 0
        assert report.lock_rate == 0.0
        assert report.usable_percentage == 0.0

    def test_excellent_quality(self):
        """Test excellent quality when DOP < 2."""
        dop_values = [1.5, 1.7, 1.8, 1.6, 1.9]
        report = _build_report(total_points=5, locked_points=5, dop_values=dop_values)

        assert report.quality_score == "excellent"
        assert report.lock_rate == 100.0
        assert report.excellent_count == 5
        assert report.good_count == 0
        assert report.usable_percentage == 100.0

    def test_good_quality(self):
        """Test good quality when DOP 2-5."""
        dop_values = [3.0, 3.5, 4.0, 2.5, 4.5]
        report = _build_report(total_points=5, locked_points=5, dop_values=dop_values)

        assert report.quality_score == "good"
        assert report.good_count == 5

    def test_ok_quality(self):
        """Test OK quality when DOP 5-10."""
        dop_values = [6.0, 7.0, 8.0, 9.0, 5.5]
        report = _build_report(total_points=5, locked_points=5, dop_values=dop_values)

        assert report.quality_score == "ok"
        assert report.moderate_count == 5

    def test_poor_quality(self):
        """Test poor quality when DOP > 10."""
        dop_values = [15.0, 20.0, 25.0, 30.0, 12.0]
        report = _build_report(total_points=5, locked_points=5, dop_values=dop_values)

        assert report.quality_score == "poor"
        assert report.poor_count == 5
        assert report.usable_percentage == 0.0

    def test_no_signal_all_invalid_dop(self):
        """Test no_signal when all DOP values are 99.99."""
        dop_values = [99.99, 99.99, 99.99]
        report = _build_report(total_points=3, locked_points=0, dop_values=dop_values)

        assert report.quality_score == "no_signal"

    def test_mixed_quality_distribution(self):
        """Test mixed quality distribution counts correctly."""
        dop_values = [1.5, 3.0, 7.0, 15.0]  # excellent, good, moderate, poor
        report = _build_report(total_points=4, locked_points=4, dop_values=dop_values)

        assert report.excellent_count == 1
        assert report.good_count == 1
        assert report.moderate_count == 1
        assert report.poor_count == 1
        assert report.usable_percentage == 75.0  # 3 out of 4

    def test_dop_statistics(self):
        """Test DOP statistics calculation."""
        dop_values = [1.0, 2.0, 3.0, 4.0, 5.0]
        report = _build_report(total_points=5, locked_points=5, dop_values=dop_values)

        assert report.dop_min == 1.0
        assert report.dop_max == 5.0
        assert report.dop_mean == 3.0
        assert report.dop_median == 3.0

    def test_lock_rate_calculation(self):
        """Test lock rate percentage calculation."""
        report = _build_report(total_points=100, locked_points=75, dop_values=[2.0] * 75)

        assert report.lock_rate == 75.0


class TestDetermineQualityScore:
    """Tests for _determine_quality_score function."""

    def test_no_lock_returns_no_signal(self):
        """Test zero lock rate returns no_signal."""
        score = _determine_quality_score(lock_rate=0, dop_mean=5.0, usable_percentage=0, dop_values=[5.0])
        assert score == "no_signal"

    def test_all_invalid_dop_returns_no_signal(self):
        """Test all invalid DOP returns no_signal."""
        score = _determine_quality_score(lock_rate=100, dop_mean=99.99, usable_percentage=0, dop_values=[99.99])
        assert score == "no_signal"

    def test_excellent_threshold(self):
        """Test excellent quality threshold."""
        score = _determine_quality_score(lock_rate=100, dop_mean=1.5, usable_percentage=100, dop_values=[1.5])
        assert score == "excellent"

    def test_good_threshold(self):
        """Test good quality threshold."""
        score = _determine_quality_score(lock_rate=100, dop_mean=3.5, usable_percentage=100, dop_values=[3.5])
        assert score == "good"

    def test_ok_threshold(self):
        """Test OK quality threshold."""
        score = _determine_quality_score(lock_rate=100, dop_mean=7.5, usable_percentage=100, dop_values=[7.5])
        assert score == "ok"

    def test_poor_threshold(self):
        """Test poor quality threshold."""
        score = _determine_quality_score(lock_rate=100, dop_mean=15.0, usable_percentage=50, dop_values=[15.0])
        assert score == "poor"


class TestGenerateWarnings:
    """Tests for _generate_warnings function."""

    def test_no_signal_warnings(self):
        """Test warnings for no_signal quality."""
        warnings = _generate_warnings(
            quality_score="no_signal",
            lock_rate=0,
            dop_mean=None,
            usable_percentage=0,
            total_points=100,
        )

        assert len(warnings) == 2
        assert "GPS signal was not acquired" in warnings[0]
        assert "external GPX" in warnings[1]

    def test_low_lock_rate_warning(self):
        """Test warning for low lock rate."""
        warnings = _generate_warnings(
            quality_score="ok",
            lock_rate=30,
            dop_mean=7.0,
            usable_percentage=80,
            total_points=100,
        )

        assert any("30%" in w for w in warnings)

    def test_poor_quality_warning(self):
        """Test warning for poor GPS quality."""
        warnings = _generate_warnings(
            quality_score="poor",
            lock_rate=100,
            dop_mean=15.0,
            usable_percentage=50,
            total_points=100,
        )

        assert any("Poor GPS quality" in w for w in warnings)
        assert any("incorrect speed" in w.lower() for w in warnings)

    def test_low_usable_percentage_warning(self):
        """Test warning for low usable percentage."""
        warnings = _generate_warnings(
            quality_score="poor",
            lock_rate=100,
            dop_mean=15.0,
            usable_percentage=30,
            total_points=100,
        )

        assert any("30%" in w for w in warnings)

    def test_ok_quality_warning(self):
        """Test warning for OK quality."""
        warnings = _generate_warnings(
            quality_score="ok",
            lock_rate=100,
            dop_mean=7.0,
            usable_percentage=100,
            total_points=100,
        )

        assert any("ok" in w.lower() for w in warnings)

    def test_excellent_no_warnings(self):
        """Test no warnings for excellent quality."""
        warnings = _generate_warnings(
            quality_score="excellent",
            lock_rate=100,
            dop_mean=1.5,
            usable_percentage=100,
            total_points=100,
        )

        assert len(warnings) == 0


class TestGPSQualityReportModel:
    """Tests for GPSQualityReport model validation."""

    def test_gps_quality_report_creation(self):
        """Test GPSQualityReport model can be created with valid data."""
        report = GPSQualityReport(
            total_points=100,
            locked_points=95,
            lock_rate=95.0,
            dop_min=1.5,
            dop_max=5.0,
            dop_mean=2.5,
            dop_median=2.3,
            excellent_count=50,
            good_count=40,
            moderate_count=10,
            poor_count=0,
            quality_score="excellent",
            usable_percentage=100.0,
            warnings=[],
        )

        assert report.total_points == 100
        assert report.quality_score == "excellent"

    def test_gps_quality_report_with_warnings(self):
        """Test GPSQualityReport with warnings list."""
        report = GPSQualityReport(
            total_points=100,
            locked_points=0,
            lock_rate=0.0,
            quality_score="no_signal",
            usable_percentage=0.0,
            warnings=["GPS signal was not acquired", "Use external GPX"],
        )

        assert len(report.warnings) == 2
        assert report.quality_score == "no_signal"

    def test_gps_quality_report_optional_fields(self):
        """Test GPSQualityReport with optional fields as None."""
        report = GPSQualityReport(
            total_points=0,
            locked_points=0,
            lock_rate=0.0,
            dop_min=None,
            dop_max=None,
            dop_mean=None,
            dop_median=None,
            quality_score="no_signal",
            usable_percentage=0.0,
        )

        assert report.dop_min is None
        assert report.dop_mean is None

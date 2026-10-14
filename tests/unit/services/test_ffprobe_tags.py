"""Tests for ffprobe tag value helpers.

Since ffmpeg 9, ffprobe joins duplicate tags with ';' — e.g. an iPhone MOV
reports creation_time = "2024-08-08T16:52:19.000000Z;2024-08-08T16:52:19.000000Z".
Parsing that as one ISO string failed, and time sync silently fell back to the
file's ctime ("file-created").
"""

import datetime

import pytest

from gpstitch.services.ffprobe_tags import first_tag_value, parse_creation_time, split_tag_values

UTC = datetime.UTC


class TestSplitTagValues:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("a", ["a"]),
            ("a;b", ["a", "b"]),
            (" a ; b ", ["a", "b"]),
            ("a;;b;", ["a", "b"]),
            ("", []),
            (None, []),
        ],
    )
    def test_splits_on_semicolon(self, value, expected):
        assert split_tag_values(value) == expected


class TestFirstTagValue:
    def test_single_value_is_returned_as_is(self):
        assert first_tag_value("15:30:37:00") == "15:30:37:00"

    def test_joined_value_yields_the_first_part(self):
        assert first_tag_value("15:30:37:00;15:30:37:00") == "15:30:37:00"

    @pytest.mark.parametrize("value", [None, "", ";"])
    def test_empty_value_is_none(self, value):
        assert first_tag_value(value) is None


class TestParseCreationTime:
    def test_parses_a_z_suffixed_value_as_utc(self):
        assert parse_creation_time("2024-08-08T16:52:19.000000Z") == datetime.datetime(
            2024, 8, 8, 16, 52, 19, tzinfo=UTC
        )

    def test_keeps_an_explicit_offset(self):
        dt = parse_creation_time("2024-08-08T19:52:19+03:00")

        assert dt.utcoffset() == datetime.timedelta(hours=3)
        assert dt == datetime.datetime(2024, 8, 8, 16, 52, 19, tzinfo=UTC)

    def test_naive_value_is_taken_as_utc(self):
        assert parse_creation_time("2024-08-08T16:52:19") == datetime.datetime(2024, 8, 8, 16, 52, 19, tzinfo=UTC)

    def test_ffmpeg9_duplicate_value(self):
        """iPhone MOV: mvhd and mdta creation_time joined by ffprobe 9."""
        value = "2024-08-08T16:52:19.000000Z;2024-08-08T16:52:19.000000Z"

        assert parse_creation_time(value) == datetime.datetime(2024, 8, 8, 16, 52, 19, tzinfo=UTC)

    def test_ffmpeg9_mixed_precision_value_takes_the_first_part(self):
        """Render output (+use_metadata_tags): mvhd in seconds, mdta with microseconds."""
        value = "2024-08-05T12:28:30.000000Z;2024-08-05T12:28:30.174000+00:00"

        assert parse_creation_time(value) == datetime.datetime(2024, 8, 5, 12, 28, 30, tzinfo=UTC)

    def test_skips_an_unparseable_part(self):
        assert parse_creation_time("garbage;2024-08-08T16:52:19Z") == datetime.datetime(
            2024, 8, 8, 16, 52, 19, tzinfo=UTC
        )

    @pytest.mark.parametrize("value", [None, "", "garbage", "garbage;also garbage"])
    def test_unparseable_value_is_none(self, value):
        assert parse_creation_time(value) is None

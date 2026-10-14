"""Reading tag values from ffprobe JSON output.

Since ffmpeg 9, ffprobe joins duplicate tags with ';' instead of keeping one of
them. A QuickTime file that carries `creation_time` both in the mvhd header and
as an mdta key (iPhone videos, or anything written with
`-movflags +use_metadata_tags`) now reports e.g.

    creation_time = "2024-08-08T16:52:19.000000Z;2024-08-08T16:52:19.000000Z"

The parts are the same instant at different precisions, so the first usable
part is taken.
"""

import datetime


def split_tag_values(value: str | None) -> list[str]:
    """Split a possibly ';'-joined tag value into its non-empty parts."""
    if not value:
        return []
    return [part.strip() for part in value.split(";") if part.strip()]


def first_tag_value(value: str | None) -> str | None:
    """Return the first part of a possibly ';'-joined tag value, or None."""
    parts = split_tag_values(value)
    return parts[0] if parts else None


def parse_creation_time(value: str | None) -> datetime.datetime | None:
    """Parse a `creation_time` tag into a timezone-aware datetime.

    Takes the first part that parses; naive values are taken as UTC, as ffmpeg
    writes them. Returns None if no part parses.
    """
    for part in split_tag_values(value):
        try:
            dt = datetime.datetime.fromisoformat(part.replace("Z", "+00:00"))
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.UTC)
        return dt
    return None

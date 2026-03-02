# Release Notes

## Version 0.6.2 — 02 Mar 2026

### ✨ Improvements

- Added CI pipeline with lint, unit/integration tests, and E2E tests on GitHub Actions
- Publish workflow gates release on passing tests before uploading to PyPI
- Screenshot images now render correctly on PyPI project page

---

## Version 0.6.1 — 02 Mar 2026

### 🆕 New

- **PyPI publishing** - Package can now be installed via `pipx install telemetry-studio`
- **Auto-open browser** - Browser opens automatically when the server starts
- **FFmpeg check at startup** - Clear error message with per-OS install instructions if FFmpeg is not found in PATH

### ✨ Improvements

- Clickable server URL in terminal output (`0.0.0.0` replaced with `127.0.0.1`)
- Updated README with pipx installation instructions

---

## Version 0.6.0 — 02 Mar 2026

### 🎉 Major Features

**DJI Camera Metrics in Overlays**

Display DJI camera metadata (ISO, shutter speed, f-number, EV, color temperature, focal length) directly in video overlays.

- **Camera metrics parsing** - SRT parser now extracts all camera fields alongside GPS data
- **Metrics preservation during render** - A wrapper-level patch intercepts GPX loading to use original SRT data, preventing loss of camera metrics during the SRT→GPX conversion
- **Custom metric accessors** - Extended gopro_overlay's metric system to support DJI-specific fields (iso, fnum, ev, ct, shutter, focal_len)

### 🆕 New

- **DJI Drone layouts** - Four resolution-specific overlay layouts (1080p, 2.7K, 4K, 5K) with speed, altitude, slope, GPS info, maps, and camera metadata widgets

### ✨ Improvements

- Failed render jobs now include last output lines in the error message for easier diagnostics
- Replaced print statements with structured logging in editor and wrapper modules
- Temp file tracking for SRT→GPX conversions is now handled by `generate_cli_command` return value instead of regex parsing
- Wrapper-internal arguments (`--ts-srt-source`, `--ts-srt-video`) are stripped from user-facing command display

### 🐞 Fixes

- Fixed missing video existence check before timezone offset estimation in SRT parser

---

## Version 0.5.0 — 28 Feb 2026

### 🎉 Major Features

**DJI Drone Support**

Full support for DJI drone video files with SRT telemetry data.

- **SRT telemetry parsing** - Parse DJI subtitle files (.srt) containing per-frame GPS coordinates, altitude, and camera metadata
- **Automatic timezone correction** - Detect timezone offset between SRT local timestamps and real UTC using video file modification time
- **Auto-detection of mtime role** - Automatically determines whether video file mtime represents the start or end of recording
- **Auto-detection of SRT files** - When a DJI video is selected, the matching `.SRT` file is automatically found and loaded
- **SRT as primary file** - Use SRT files directly in overlay-only mode (no video required)

### ✨ Improvements

- GPS quality analysis now works for external GPX and FIT telemetry files
- Secondary file validation accepts SRT alongside GPX and FIT formats

---

## Version 0.4.1 — 28 Feb 2026

### ✨ Improvements

- **Version display in UI** - Application version is now shown in the interface
- **Fix project name** - Updated branding across all UI elements
- **Static asset caching** - Added no-cache headers to prevent stale assets after updates

---

## Version 0.4.0 — 27 Feb 2026

### 🎉 Major Features

**Non-GoPro Video Support**

Full support for non-GoPro video files with external GPS data.

- **MOV format support** - Upload and render `.mov` video files alongside existing formats
- **External GPX/FIT fallback** - Automatically use external GPS data when video has no embedded telemetry
- **Video rotation handling** - Detect and apply correct rotation for videos with non-standard orientation
- **Order-independent uploads** - Upload GPX/FIT file first, then video — the session is reused instead of creating a new one

### 🐞 Fixes

- Fixed pillarbox temp file timestamp being set to current time, breaking GPS time alignment with `--video-time-start file-modified`
- Fixed pillarbox/letterbox preview now uses fit-to-canvas instead of stretch

---

## Version 0.3.0 — 04 Feb 2026

### 🎉 Major Features

**GPS Quality Analysis**

Automatic GPS signal quality analysis for uploaded videos with visual feedback and warnings before rendering.

- **Quality scoring** - Analyzes GPS lock rate and DOP (Dilution of Precision) values to classify signal quality as Excellent, Good, OK, Poor, or No Signal
- **Quality indicator in header** - Compact badge shows current GPS quality with detailed tooltip
- **Quality distribution card** - Visual breakdown of GPS point quality with statistics (DOP average, lock rate, usable percentage)
- **Pre-render warnings** - Modal warns before rendering files with poor GPS quality, explaining potential overlay issues
- **Batch quality check** - Table view of GPS quality for all files in batch render, with option to skip files with issues

### 🆕 New

- **Overwrite confirmation dialog** - Shows list of existing files before batch render with Skip Existing option

### ✨ Improvements

- GPS filter settings (DOP max, speed max) added to rendering parameters

---

## Version 0.2.0

Initial feature release with GPS filter settings.

---

## Version 0.1.0

Initial release.

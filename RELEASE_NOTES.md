# Release Notes

## Version 0.15.0 — 14 Apr 2026

### 🐞 Fixes

- Fixed orientation widgets (Pitch, Roll, Yaw) rendering as tiny empty rectangles in CLI renders — the subprocess was not loading CORI/ACCL/GRAV tracks from GoPro GPMF data, while the editor preview worked correctly ([#15](https://github.com/Romancha/GPStitch/issues/15))
- Fixed startup crash when unrecognized environment variables with `GPSTITCH_` prefix are present ([#3](https://github.com/Romancha/GPStitch/issues/3))

---

## Version 0.14.2 — 10 Apr 2026

### ✨ Improvements

- **Canvas size mismatch warning** — Advanced Mode now shows an informational banner when the editor's template canvas dimensions don't match the loaded video's resolution, so users understand why widgets may appear misplaced in the rendered output

### 🐞 Fixes

- Fixed custom templates rendering at the wrong overlay size — `--overlay-size` is now read from the template's sidecar metadata instead of falling back to a hardcoded 1920×1080, which caused widget misalignment for any canvas dimensions other than default
- Fixed predefined template canvas dimensions being estimated from widget bounding boxes instead of the layout's true size (e.g. `default-3840x2160` now correctly reports 3840×2160)

---

## Version 0.14.1 — 10 Apr 2026

### 🎉 Major Features

**Time Sync Algorithm Rewrite**

Replaced the midpoint-based timezone auto-correction with a robust enumerate-based cascade. The old algorithm failed for the common workflow of short video clips inside long GPS tracks (e.g., a 2-minute Insta360 clip inside a 1-hour Garmin track). The new algorithm reliably handles this scenario. ([#9](https://github.com/Romancha/GPStitch/issues/9))

- **System timezone as primary signal** — GPStitch now uses your machine's local timezone offset as the first correction candidate, which matches the recording timezone in most local workflows
- **Exhaustive overlap search** — If system timezone doesn't match, GPStitch tries all valid whole-hour and fractional timezone offsets and picks any unique match automatically
- **Failure with suggested offset** — When auto-correction can't determine the right offset, the UI shows an actionable error with a "Switch to Manual" button pre-filled with the best-guess offset

### ✨ Improvements

- **Transparent correction banners** — Info banner when system timezone was applied, warning banner for exhaustive search results, error banner with one-click Manual fallback when auto fails
- **Manual Offset panel redesign** — Replaced single-line display with three labeled rows (Original creation_time / Corrected video start / GPS range) for clarity ([#11](https://github.com/Romancha/GPStitch/issues/11))

### 🐞 Fixes

- Fixed timezone auto-correction failing for short video clips inside long GPS tracks — the midpoint-based guard incorrectly rejected valid corrections when video and GPS durations differed significantly ([#9](https://github.com/Romancha/GPStitch/issues/9))

---

## Version 0.14.0 — 09 Apr 2026

### 🆕 New

- **Timezone auto-correction for non-GoPro cameras** — Automatically detects and corrects UTC offset when video `creation_time` lacks timezone info, improving time alignment with external GPS data ([#9](https://github.com/Romancha/GPStitch/issues/9))
- **Independent video and GPS file fields** — Video and GPS files are now decoupled in the upload UI; replacing the video no longer clears the GPS file ([#10](https://github.com/Romancha/GPStitch/issues/10))
- **Degree unit for orientation metrics** — Pitch, Roll, and Yaw widgets now support a degree (°) unit option ([#14](https://github.com/Romancha/GPStitch/issues/14))

### ✨ Improvements

- **Manual Offset panel refinements** — Seconds are now displayed in the time preview, and Video/GPS labels clarify which timestamp is which ([#11](https://github.com/Romancha/GPStitch/issues/11))
- **Time Sync mode descriptions** — Each sync mode (Auto, GPX Timestamps, Manual) now shows an inline explanation in the UI ([#11](https://github.com/Romancha/GPStitch/issues/11))

### 🐞 Fixes

- Fixed `creation_time` timezone validation rejecting valid non-GoPro videos when the metadata timestamp had no UTC indicator ([#9](https://github.com/Romancha/GPStitch/issues/9))

---

## Version 0.13.0 — 29 Mar 2026

### 🆕 New

- **Independent video and GPS file selection** — Video and GPS file fields are now fully decoupled; changing the video file no longer clears the GPS file, making it easier to mix and match files ([#10](https://github.com/Romancha/GPStitch/issues/10))

### ✨ Improvements

- Added Time Sync mode descriptions to the UI for better discoverability ([#11](https://github.com/Romancha/GPStitch/issues/11))

### 🐞 Fixes

- Fixed incorrect timezone detection for non-GoPro cameras (e.g. Insta360) where `creation_time` is written as local time but reported as UTC — now cross-validates against GPS data and falls back to file mtime ([#9](https://github.com/Romancha/GPStitch/issues/9))

---

## Version 0.12.1 — 21 Mar 2026

### 🆕 New

- **`gpstitch-dashboard` CLI command** — Standalone entry point that works as a drop-in replacement for `gopro-dashboard.py` with all GPStitch patches applied (DJI support, timecode preservation, audio copy, etc.). Use the "Get Command" button in the UI to generate a ready-to-run command ([#5](https://github.com/Romancha/GPStitch/issues/5))

### 🐞 Fixes

- Fixed README showing Python 3.14+ requirement instead of 3.12+ ([#4](https://github.com/Romancha/GPStitch/issues/4))

---

## Version 0.12.0 — 17 Mar 2026

### 🎉 Major Features

**DJI Osmo Action Embedded GPS Support**

Full support for DJI Osmo Action cameras (Action 4/5/6) with DJI GPS Bluetooth Remote Controller — no secondary GPX or SRT file needed.

- **Automatic detection** — Embedded GPS telemetry is identified during upload and shown in the UI
- **Protobuf decoder** — Extracts GPS data from the DJI meta stream (`djmd` codec) embedded in video files
- **End-to-end pipeline** — Preview, render, and CLI command generation all work with embedded GPS data out of the box
- **GPX export** — Extracted GPS is converted to timeseries and GPX for use in the overlay engine

---

## Version 0.11.0 — 16 Mar 2026

### 🐞 Fixes

- Fixed output file always getting `.mp4` extension regardless of FFmpeg profile, causing import failures in Final Cut Pro and DaVinci Resolve — now uses `.mov` for PNG codec and `.webm` for VP8/VP9 with alpha channel ([#12](https://github.com/Romancha/GPStitch/issues/12))

---

## Version 0.10.2 — 13 Mar 2026

### 🐞 Fixes

- Made `pycairo` an optional dependency so `pipx install gpstitch` succeeds on systems without cairo system libraries ([#5](https://github.com/Romancha/GPStitch/issues/5))
  - Cairo layouts (`example`, `example-2`) are now detected at runtime and shown as unavailable in the UI when pycairo is not installed
  - Install with cairo support: `pipx install 'gpstitch[cairo]'` or add to existing: `pipx inject gpstitch pycairo`

---

## Version 0.10.1 — 12 Mar 2026

### 🐞 Fixes

- Fixed DJI drone preview crash caused by UTC/local timezone mismatch in time alignment — preview now correctly estimates the UTC offset and converts to the SRT local time domain ([#7](https://github.com/Romancha/GPStitch/issues/7))
- Fixed cairo-based layouts (e.g. `example`, `example-2`) failing with "This widget needs pycairo" — added missing `pycairo` dependency ([#5](https://github.com/Romancha/GPStitch/issues/5))

---

## Version 0.10.0 — 12 Mar 2026

### 🎉 Major Features

**Shared GPX Batch Render with Odometer Offset**
- Batch render multiple videos against a single shared GPX track, with each video receiving an odometer offset calculated from its creation time relative to the track start
- Overlay shows absolute distance from the beginning of the track, not relative to each video segment

### 🆕 New

- **Timeseries processing for external GPX/FIT files** — Derived metrics (speed, distance, cumulative odometer) are now computed for external telemetry files, matching the processing pipeline used for GoPro data

### 🐞 Fixes

- Fixed `zone_bar` and `bar` widgets ignoring x/y position in the visual editor — they are now wrapped in `<translate>` elements automatically
- Fixed CLI command generation using `--layout` instead of `--layout-xml` for non-builtin layouts, causing gopro-dashboard.py to reject alternate layout names

---

## Version 0.9.0 — 10 Mar 2026

### 🎉 Major Features

**Time Sync for External GPX Files**
- Align non-GoPro video timestamps with external GPX track data using three explicit modes: **auto** (extract creation time from video metadata), **gpx-timestamps** (use GPX data as-is without alignment), and **manual** (auto-detected time with a user-specified offset in seconds)
- Manual mode adds +/- controls and direct offset input so users can fine-tune alignment frame by frame
- Time offset is applied consistently through preview and render pipelines

---

## Version 0.8.0 — 05 Mar 2026

### ✨ Improvements

- **Python 3.12+ support** — Lowered minimum Python version from 3.14 to 3.12, making GPStitch installable on Ubuntu 24.04 LTS and other systems without bleeding-edge Python ([#4](https://github.com/Romancha/GPStitch/issues/4))

---

## Version 0.7.1 — 03 Mar 2026

### ✨ Improvements

- **Stitch Blue design system** — Updated color scheme across all views to match the new GPStitch brand identity (accent color, navy backgrounds, softer border-radius)
- **Favicon and logo** — Added GPS-pin favicon with Stitch ears to browser tabs; inline logo in all page headers
- **Dark theme for classic view** — Classic interface now uses the same dark theme as the main UI
- **Self-hosted JetBrains Mono** — Monospace font served locally, no external CDN dependency

### 🐞 Fixes

- Fixed header and toolbar buttons (Export XML, Batch Render, Save, Upload, Manage, etc.) disappearing off-screen on narrow windows — they now wrap to the next line
- Fixed unreadable white text on light-blue accent buttons and widget labels
- Fixed selected widget glow using old cyan color instead of brand blue
- Fixed editor page title still showing "GoPro Overlay"
- Fixed tooltip and canvas using neutral grey instead of navy palette

---

## Version 0.7.0 — 03 Mar 2026

- Rename project to GPStitch

## Version 0.6.5 — 02 Mar 2026

### 🐞 Fixes

- Fixed gopro-dashboard.py not found when installed via pipx (search in Python executable's bin directory)

---

## Version 0.6.4 — 02 Mar 2026

### 🐞 Fixes

- Fixed startup crash with setuptools 82+ (pin setuptools<82 to keep pkg_resources for geotiler)
- Fixed browser opening before server is ready — now opens after uvicorn startup completes

---

## Version 0.6.3 — 02 Mar 2026

### 🐞 Fixes

- Fixed startup crash when installed via pipx on Python 3.14 (missing `pkg_resources`)

---

## Version 0.6.2 — 02 Mar 2026

### ✨ Improvements

- Added CI pipeline with lint, unit/integration tests, and E2E tests on GitHub Actions
- Publish workflow gates release on passing tests before uploading to PyPI
- Screenshot images now render correctly on PyPI project page

---

## Version 0.6.1 — 02 Mar 2026

### 🆕 New

- **PyPI publishing** - Package can now be installed via `pipx install gpstitch`
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

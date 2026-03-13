"""Video rendering service using gopro-dashboard.py subprocess."""

import asyncio
import contextlib
import logging
import os
import re
import shlex
import signal
import sys
from datetime import UTC
from pathlib import Path

from gpstitch.config import settings
from gpstitch.models.job import JobStatus, RenderJobConfig
from gpstitch.services.job_manager import job_manager
from gpstitch.services.renderer import generate_cli_command

# Apply runtime patches if enabled
if settings.enable_gopro_patches:
    from gpstitch.patches import apply_patches

    apply_patches()

logger = logging.getLogger(__name__)


class RenderService:
    """Handles video rendering as background subprocess."""

    def __init__(self):
        self._process: asyncio.subprocess.Process | None = None
        self._current_job_id: str | None = None
        self._lock = asyncio.Lock()

    async def _kill_process_tree(self):
        """Kill the current process and all its children (ffmpeg, etc.)."""
        if not self._process:
            return
        pid = self._process.pid
        try:
            if sys.platform != "win32":
                # Kill entire process group on Unix
                os.killpg(pid, signal.SIGKILL)
            else:
                self._process.kill()
            await self._process.wait()
        except ProcessLookupError:
            pass  # Process already dead
        except Exception:
            pass

    @staticmethod
    def _get_gpx_start_timestamp(gpx_path: str) -> float | None:
        """Extract the first trackpoint timestamp from a GPX file as Unix timestamp."""
        try:
            import xml.etree.ElementTree as ET

            tree = ET.parse(gpx_path)
            root = tree.getroot()
            # Handle GPX namespace
            ns = {"gpx": "http://www.topografix.com/GPX/1/1"}
            # Try with namespace first, then without
            time_elem = root.find(".//gpx:trkpt/gpx:time", ns)
            if time_elem is None:
                time_elem = root.find(
                    ".//{http://www.topografix.com/GPX/1/1}trkpt/{http://www.topografix.com/GPX/1/1}time"
                )
            if time_elem is None:
                # Try without namespace
                time_elem = root.find(".//trkpt/time")
            if time_elem is not None and time_elem.text:
                from datetime import datetime

                time_str = time_elem.text.strip()
                # Parse ISO 8601 format (e.g., "2026-01-26T17:36:54.000Z")
                if time_str.endswith("Z"):
                    time_str = time_str[:-1] + "+00:00"
                dt = datetime.fromisoformat(time_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                return dt.timestamp()
        except Exception as e:
            logger.warning(f"Failed to parse GPX start time from {gpx_path}: {e}")
        return None

    @staticmethod
    def _get_srt_start_timestamp(srt_path: str) -> float | None:
        """Extract the first GPS timestamp from a DJI SRT file as Unix timestamp.

        Note: SRT timestamps are naive local time, so the returned Unix timestamp
        treats them as local system time. This is primarily used for relative
        time alignment, not absolute UTC positioning.
        """
        try:
            from gpstitch.services.srt_parser import parse_srt

            points = parse_srt(Path(srt_path))
            if points:
                return points[0].dt.timestamp()
        except Exception as e:
            logger.warning(f"Failed to parse SRT start time from {srt_path}: {e}")
        return None

    def _resolve_mtime_for_alignment(self, config: RenderJobConfig, video_path: str) -> float | None:
        """Resolve the target mtime for time alignment modes.

        For "auto"/"manual": extract creation_time via ffprobe, fallback to st_ctime,
        apply time_offset_seconds for manual mode. Returns Unix timestamp.
        For "file-modified" (SRT legacy): resolve based on secondary file type.
        Returns None if no mtime change is needed.
        """
        from gpstitch.services.file_manager import file_manager

        # For SRT secondary, the renderer forces "file-modified" alignment using
        # the video's original mtime (which DJI sets to recording start or end).
        # Do NOT override mtime in auto/manual mode when SRT is secondary.
        secondary = file_manager.get_secondary_file(config.session_id)
        is_srt = secondary and secondary.file_type == "srt"

        if config.video_time_alignment in ("auto", "manual") and not is_srt:
            from gpstitch.services.renderer import _extract_creation_time

            creation_time = _extract_creation_time(Path(video_path))
            if creation_time is not None:
                ts = creation_time.timestamp()
            else:
                from gopro_overlay.ffmpeg_gopro import filestat

                fstat = filestat(Path(video_path))
                ts = fstat.ctime.timestamp()

            if config.video_time_alignment == "manual" and config.time_offset_seconds:
                ts += config.time_offset_seconds
            return ts

        if config.video_time_alignment == "file-modified" or is_srt:
            if secondary and secondary.file_type in ("gpx", "fit"):
                return self._get_gpx_start_timestamp(secondary.file_path)
            elif is_srt:
                return os.stat(video_path).st_mtime
        return None

    def _needs_pillarbox(self, video_path: str, config: RenderJobConfig) -> tuple[int, int, int, int] | None:
        """Check if video needs pillarboxing to fit the canvas.

        Returns (canvas_w, canvas_h, video_w, video_h) if pillarboxing is needed, None otherwise.
        """
        try:
            from gopro_overlay.ffmpeg import FFMPEG
            from gopro_overlay.ffmpeg_gopro import FFMPEGGoPro

            from gpstitch.services.metadata import get_display_dimensions, get_video_rotation
            from gpstitch.services.renderer import get_available_layouts

            # Get video dimensions
            ffmpeg = FFMPEG()
            ffmpeg_gopro = FFMPEGGoPro(ffmpeg)
            recording = ffmpeg_gopro.find_recording(Path(video_path))
            rotation = get_video_rotation(Path(video_path))
            video_w, video_h = get_display_dimensions(
                recording.video.dimension.x, recording.video.dimension.y, rotation
            )

            # Get canvas dimensions from layout
            layout_info = None
            for info in get_available_layouts():
                if info.name == config.layout:
                    layout_info = info
                    break
            if layout_info is None:
                layout_info = get_available_layouts()[0]

            canvas_w, canvas_h = layout_info.width, layout_info.height

            # Check if aspect ratios differ
            video_aspect = video_w / video_h
            canvas_aspect = canvas_w / canvas_h
            if abs(video_aspect - canvas_aspect) < 0.01:
                return None

            return canvas_w, canvas_h, video_w, video_h
        except Exception as e:
            logger.warning(f"Failed to check pillarbox need: {e}")
            return None

    async def _create_pillarboxed_video(
        self, video_path: str, canvas_w: int, canvas_h: int, video_w: int, video_h: int, job_id: str
    ) -> str | None:
        """Create a temporary pillarboxed version of the video using FFmpeg.

        Returns the path to the temp file, or None if pre-processing failed.
        """
        # Calculate scale to fit within canvas preserving aspect ratio
        scale = min(canvas_w / video_w, canvas_h / video_h)
        new_w = int(video_w * scale)
        new_h = int(video_h * scale)
        # Ensure even dimensions (required by most codecs)
        new_w = new_w - (new_w % 2)
        new_h = new_h - (new_h % 2)

        pad_x = (canvas_w - new_w) // 2
        pad_y = (canvas_h - new_h) // 2

        # Create temp file in the same directory as the video
        video_dir = os.path.dirname(video_path)
        video_name = os.path.splitext(os.path.basename(video_path))[0]
        temp_path = os.path.join(video_dir, f".{video_name}_pillarbox_temp.mp4")

        vf = f"scale={new_w}:{new_h},pad={canvas_w}:{canvas_h}:{pad_x}:{pad_y}"

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            video_path,
            "-vf",
            vf,
            "-c:a",
            "copy",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "18",
            temp_path,
        ]

        await job_manager.append_job_log(job_id, "=== Pillarbox Pre-processing ===")
        await job_manager.append_job_log(job_id, f"Video: {video_w}x{video_h} → Canvas: {canvas_w}x{canvas_h}")
        await job_manager.append_job_log(job_id, f"FFmpeg filter: {vf}")
        await job_manager.append_job_log(job_id, f"Running: {shlex.join(cmd)}")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await process.communicate()

            if process.returncode == 0:
                # Preserve original video's mtime (needed for --video-time-start file-modified)
                original_stat = os.stat(video_path)
                os.utime(temp_path, (original_stat.st_atime, original_stat.st_mtime))
                await job_manager.append_job_log(job_id, "Pillarbox pre-processing completed")
                return temp_path

            else:
                output = stdout.decode("utf-8", errors="replace") if stdout else ""
                await job_manager.append_job_log(job_id, f"Pillarbox pre-processing failed: {output[-500:]}")
                logger.error(f"FFmpeg pillarbox failed for job {job_id}: {output[-500:]}")
                return None
        except Exception as e:
            await job_manager.append_job_log(job_id, f"Pillarbox pre-processing error: {e}")
            logger.error(f"FFmpeg pillarbox error for job {job_id}: {e}")
            return None

    async def start_render(self, job_id: str, config: RenderJobConfig):
        """Start rendering process for a job."""

        # Check if already rendering (with lock for race safety)
        async with self._lock:
            if self._current_job_id is not None and self._current_job_id != job_id:
                logger.warning(f"Cannot start job {job_id}: another job is running ({self._current_job_id})")
                return
            # Claim the slot (or confirm already pre-claimed by _start_next_pending_job)
            self._current_job_id = job_id

        # Helper to clear current job on early failure
        async def _clear_current_job():
            async with self._lock:
                self._process = None
                self._current_job_id = None
            await self._start_next_pending_job()

        # Generate CLI command
        try:
            command, srt_gpx_temp_files = generate_cli_command(
                session_id=config.session_id,
                output_file=config.output_file,
                layout=config.layout,
                layout_xml_path=config.layout_xml_path,
                units_speed=config.units_speed,
                units_altitude=config.units_altitude,
                units_distance=config.units_distance,
                units_temperature=config.units_temperature,
                map_style=config.map_style,
                gpx_merge_mode=config.gpx_merge_mode,
                video_time_alignment=config.video_time_alignment,
                ffmpeg_profile=config.ffmpeg_profile,
                gps_dop_max=config.gps_dop_max,
                gps_speed_max=config.gps_speed_max,
                odo_offset=config.odo_offset,
            )
        except Exception as e:
            error_msg = f"Failed to generate command: {e}"
            await job_manager.append_job_log(job_id, f"ERROR: {error_msg}")
            await job_manager.update_job_status(job_id, JobStatus.FAILED, error_msg)
            logger.error(f"Failed to generate command for job {job_id}: {e}")
            await _clear_current_job()
            return

        # Check if layout requires cairo and pycairo is available
        from gpstitch.constants import PYCAIRO_INSTALL_HINT, is_pycairo_available
        from gpstitch.services.renderer import _layout_requires_cairo

        layout_name = config.layout
        layout_xml = config.layout_xml_path
        needs_cairo = False
        if layout_xml:
            with contextlib.suppress(OSError):
                needs_cairo = "cairo" in Path(layout_xml).read_text().lower()
        else:
            needs_cairo = _layout_requires_cairo(layout_name)

        if needs_cairo and not is_pycairo_available():
            error = PYCAIRO_INSTALL_HINT
            await job_manager.update_job_status(job_id, JobStatus.FAILED, error)
            logger.error(f"Job {job_id}: pycairo not available for cairo layout '{layout_name}'")
            await _clear_current_job()
            return

        # Find gopro-dashboard.py location
        gopro_dashboard = self._find_gopro_dashboard()
        if not gopro_dashboard:
            error = "gopro-dashboard.py not found"
            await job_manager.update_job_status(job_id, JobStatus.FAILED, error)
            logger.error(f"Job {job_id}: {error}")
            await _clear_current_job()
            return

        # Collect temp files for cleanup
        pillarbox_temp_file = None
        restore_mtime_info = None  # (path, atime, mtime) to restore after render

        # Check if video needs pillarboxing (aspect ratio mismatch with canvas)
        from gpstitch.services.file_manager import file_manager

        primary = file_manager.get_primary_file(config.session_id)
        secondary = file_manager.get_secondary_file(config.session_id)
        # mtime manipulation is only needed when there's a secondary file (merge mode),
        # because video-only renders (Mode 1) don't use --video-time-start.
        needs_mtime = secondary is not None
        if primary and primary.file_type == "video":
            pillarbox_info = self._needs_pillarbox(primary.file_path, config)
            if pillarbox_info:
                canvas_w, canvas_h, video_w, video_h = pillarbox_info
                await job_manager.update_job_status(job_id, JobStatus.RUNNING)
                pillarbox_temp_file = await self._create_pillarboxed_video(
                    primary.file_path, canvas_w, canvas_h, video_w, video_h, job_id
                )
                if pillarbox_temp_file:
                    # Set mtime on pillarbox file for time alignment.
                    # gopro-dashboard uses --video-time-start file-modified which reads mtime.
                    target_ts = self._resolve_mtime_for_alignment(config, primary.file_path) if needs_mtime else None
                    if target_ts:
                        os.utime(pillarbox_temp_file, (target_ts, target_ts))
                        await job_manager.append_job_log(
                            job_id,
                            "Set pillarbox file mtime for time alignment",
                        )
                    # Replace video path in command with pillarboxed version
                    command = command.replace(shlex.quote(primary.file_path), shlex.quote(pillarbox_temp_file))
            else:
                # No pillarbox — set mtime on original video if needed
                # (save and restore after render)
                target_ts = self._resolve_mtime_for_alignment(config, primary.file_path) if needs_mtime else None
                if target_ts:
                    original_stat = os.stat(primary.file_path)
                    os.utime(primary.file_path, (target_ts, target_ts))
                    restore_mtime_info = (primary.file_path, original_stat.st_atime, original_stat.st_mtime)
                    await job_manager.append_job_log(
                        job_id,
                        "Set video file mtime for time alignment",
                    )

        # Parse command into args
        try:
            args = shlex.split(command)
            # Replace script name with full path
            args[0] = str(gopro_dashboard)
        except Exception as e:
            await job_manager.update_job_status(job_id, JobStatus.FAILED, f"Failed to parse command: {e}")
            if restore_mtime_info:
                path, atime, mtime = restore_mtime_info
                with contextlib.suppress(OSError):
                    os.utime(path, (atime, mtime))
            if pillarbox_temp_file:
                self._cleanup_temp_file(pillarbox_temp_file)
            await _clear_current_job()
            return

        logger.info(f"Starting render job {job_id}")
        logger.info(f"Generated command: {command}")
        logger.info(f"Parsed args: {args}")

        await job_manager.update_job_status(job_id, JobStatus.RUNNING)

        # Log the command to job logs for UI visibility
        await job_manager.append_job_log(job_id, "=== Command ===")
        # Use shlex.join to properly quote paths with spaces
        await job_manager.append_job_log(job_id, f"{sys.executable} {shlex.join(args)}")
        await job_manager.append_job_log(job_id, "=== Output ===")

        try:
            # Start subprocess in new session (Unix) to enable killing entire process group
            # This ensures child processes (ffmpeg) are also terminated on cancel
            self._process = await asyncio.create_subprocess_exec(
                sys.executable,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=self._get_process_env(),
                start_new_session=True,
            )

            await job_manager.set_job_pid(job_id, self._process.pid)
            logger.info(f"Job {job_id} started with PID {self._process.pid}")

            # Stream output and parse progress
            await self._stream_output(job_id)

            # Wait for completion
            returncode = await self._process.wait()

            if returncode == 0:
                await job_manager.update_job_status(job_id, JobStatus.COMPLETED)
                await job_manager.update_job_progress(job_id, 100)
                logger.info(f"Job {job_id} completed successfully")
            else:
                # Include last output lines in error for better diagnostics
                job = await job_manager.get_job(job_id)
                last_lines = []
                if job and job.log_lines:
                    # Get last non-empty output lines (skip command header)
                    for line in reversed(job.log_lines):
                        if line.startswith("=== ") or not line.strip():
                            continue
                        last_lines.insert(0, line.strip())
                        if len(last_lines) >= 3:
                            break
                tail = ": " + " | ".join(last_lines) if last_lines else ""
                error = f"Process exited with code {returncode}{tail}"
                await job_manager.append_job_log(job_id, "\n=== Failed ===")
                await job_manager.append_job_log(job_id, error)
                await job_manager.update_job_status(job_id, JobStatus.FAILED, error)
                logger.error(f"Job {job_id} failed: {error}")

        except asyncio.CancelledError:
            # Kill the subprocess and all children before marking as cancelled
            await self._kill_process_tree()
            await job_manager.update_job_status(job_id, JobStatus.CANCELLED)
            logger.info(f"Job {job_id} cancelled")
            raise
        except Exception as e:
            # Kill subprocess and all children on error
            await self._kill_process_tree()
            await job_manager.update_job_status(job_id, JobStatus.FAILED, str(e))
            logger.exception(f"Job {job_id} failed with exception")
        finally:
            # Restore original mtime if we changed it
            if restore_mtime_info:
                path, atime, mtime = restore_mtime_info
                with contextlib.suppress(OSError):
                    os.utime(path, (atime, mtime))
            # Clean up temp files
            if pillarbox_temp_file:
                self._cleanup_temp_file(pillarbox_temp_file)
            for temp_gpx in srt_gpx_temp_files:
                self._cleanup_temp_file(temp_gpx)
            async with self._lock:
                self._process = None
                self._current_job_id = None
            # Auto-start next pending job if exists (for batch processing)
            await self._start_next_pending_job()

    async def _start_next_pending_job(self):
        """Start the next pending job in queue if exists (with lock protection)."""
        next_job = None
        async with self._lock:
            # Double-check no job is running before starting next
            if self._current_job_id is not None:
                return
            next_job = await job_manager.get_next_pending_job()
            if next_job:
                logger.info(f"Auto-starting next pending job: {next_job.id}")
                # Set current job ID immediately to prevent races
                self._current_job_id = next_job.id

        # Start render outside of lock (but we've claimed the slot)
        if next_job:
            # Don't use create_task - run synchronously to properly await
            await self.start_render(next_job.id, next_job.config)

    async def _stream_output(self, job_id: str):
        """Stream subprocess output and parse progress."""
        if not self._process or not self._process.stdout:
            return

        # Full pattern for gopro-dashboard.py output:
        # "Render: 22 [  0%]  [  6.8/s] |...| ETA:   0:07:33"
        render_pattern = re.compile(r"Render:\s*([\d,]+)\s*\[\s*(\d+)%\]\s*\[\s*([\d.]+)/s\].*?ETA:\s*(\d+:\d+:\d+)")

        # Simpler fallback patterns
        progress_patterns = [
            # Pattern 1: "Render: 1234 [ 56%]" with spaces inside brackets
            re.compile(r"Render:\s*([\d,]+)\s*\[\s*(\d+)%\]"),
            # Pattern 2: Any percentage in brackets with possible spaces
            re.compile(r"\[\s*(\d+(?:\.\d+)?)%\]"),
            # Pattern 3: Frame X/Y format
            re.compile(r"Frame\s+(\d+)/(\d+)"),
            # Pattern 4: frame= from ffmpeg
            re.compile(r"frame=\s*(\d+)"),
        ]

        # Total frames pattern (from timeseries info)
        total_pattern = re.compile(r"(\d+)\s*(?:frames|data points)")

        total_frames = None

        async for line in self._process.stdout:
            line_str = line.decode("utf-8", errors="replace").strip()
            if not line_str:
                continue

            # Append to log
            await job_manager.append_job_log(job_id, line_str)

            # Try to extract total frames
            if total_frames is None:
                total_match = total_pattern.search(line_str)
                if total_match:
                    total_frames = int(total_match.group(1))

            # Try full render pattern first (includes FPS and ETA)
            render_match = render_pattern.search(line_str)
            if render_match:
                current_frame = int(render_match.group(1).replace(",", ""))
                percent = float(render_match.group(2))
                fps = float(render_match.group(3))
                eta_str = render_match.group(4)  # "0:07:33"
                # Parse ETA to seconds
                parts = eta_str.split(":")
                eta_seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])

                await job_manager.update_job_progress(
                    job_id,
                    percent=percent,
                    current_frame=current_frame,
                    total_frames=total_frames,
                    fps=fps,
                    eta_seconds=eta_seconds,
                )
                continue

            # Fallback to simpler patterns
            for pattern in progress_patterns:
                match = pattern.search(line_str)
                if match:
                    groups = match.groups()
                    if len(groups) == 1:
                        # Percentage or frame count
                        value = float(groups[0])
                        if value <= 100:
                            await job_manager.update_job_progress(
                                job_id,
                                percent=value,
                                total_frames=total_frames,
                            )
                        else:
                            current_frame = int(value)
                            percent = (current_frame / total_frames * 100) if total_frames else 0
                            await job_manager.update_job_progress(
                                job_id,
                                percent=percent,
                                current_frame=current_frame,
                                total_frames=total_frames,
                            )
                    elif len(groups) == 2:
                        # Render pattern: frame, percent or Frame X/Y format
                        try:
                            current_frame = int(groups[0].replace(",", ""))
                            percent = float(groups[1])
                            await job_manager.update_job_progress(
                                job_id,
                                percent=percent,
                                current_frame=current_frame,
                                total_frames=total_frames,
                            )
                        except ValueError:
                            pass
                    break

    async def cancel_render(self, job_id: str) -> bool:
        """Cancel a running render job."""
        if self._current_job_id != job_id:
            logger.warning(f"Cannot cancel job {job_id}: not the current job")
            return False

        if not self._process:
            logger.warning(f"Cannot cancel job {job_id}: no process running")
            return False

        pid = self._process.pid
        logger.info(f"Cancelling job {job_id} (PID {pid})")

        try:
            # Kill entire process group (includes child processes like ffmpeg)
            # On Unix, start_new_session=True creates a new process group with pgid=pid
            if sys.platform != "win32":
                try:
                    os.killpg(pid, signal.SIGTERM)
                    logger.info(f"Sent SIGTERM to process group {pid}")
                except ProcessLookupError:
                    pass  # Process group already dead

            # Wait up to 5 seconds for graceful termination
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except TimeoutError:
                # Force kill the entire process group
                logger.warning(f"Force killing job {job_id}")
                if sys.platform != "win32":
                    with contextlib.suppress(ProcessLookupError):
                        os.killpg(pid, signal.SIGKILL)
                else:
                    self._process.kill()
                await self._process.wait()

            await job_manager.update_job_status(job_id, JobStatus.CANCELLED)
            return True

        except ProcessLookupError:
            # Process already dead
            logger.info(f"Job {job_id} process already terminated")
            return True
        except Exception:
            logger.exception(f"Error cancelling job {job_id}")
            return False

    @staticmethod
    def _cleanup_temp_file(temp_path: str):
        """Remove temporary file."""
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
                logger.info(f"Cleaned up temp file: {temp_path}")
        except Exception as e:
            logger.warning(f"Failed to clean up temp file {temp_path}: {e}")

    def _find_gopro_dashboard(self) -> Path | None:
        """Locate gopro-dashboard.py script or wrapper.

        If wrapper script is enabled in settings, returns the wrapper which
        applies runtime patches before executing the original gopro-dashboard.py.
        """
        # If wrapper script is enabled, use it to ensure patches are applied
        if settings.use_wrapper_script:
            wrapper_path = Path(__file__).parent.parent / "scripts" / "gopro_dashboard_wrapper.py"
            if wrapper_path.exists():
                logger.info(f"Using wrapper script: {wrapper_path}")
                return wrapper_path
            else:
                logger.warning(f"Wrapper script not found at {wrapper_path}, falling back to original")

        # Check bin/ directory relative to project root
        current_file = Path(__file__)
        # Navigate from services/ up to project root
        project_root = current_file.parents[3]  # services -> gpstitch -> src -> project
        bin_script = project_root / "bin" / "gopro-dashboard.py"
        if bin_script.exists():
            return bin_script

        # Check same directory as Python executable (pipx/venv installs)
        import sys

        python_bin_dir = Path(sys.executable).parent
        venv_script = python_bin_dir / "gopro-dashboard.py"
        if venv_script.exists():
            return venv_script

        # Check PATH
        import shutil

        path_script = shutil.which("gopro-dashboard.py")
        if path_script:
            return Path(path_script)

        return None

    def _get_process_env(self) -> dict:
        """Get environment variables for subprocess."""
        env = os.environ.copy()

        # Disable Python output buffering to ensure all output is captured
        env["PYTHONUNBUFFERED"] = "1"

        # Set PYTHONPATH to include project root
        current_file = Path(__file__)
        project_root = current_file.parents[3]

        pythonpath = env.get("PYTHONPATH", "")
        if pythonpath:
            env["PYTHONPATH"] = f"{project_root}:{pythonpath}"
        else:
            env["PYTHONPATH"] = str(project_root)

        return env


# Global render service instance
render_service = RenderService()

import subprocess
import json
import copy
import re
import time
from ffmpeg_builder import build_ffmpeg_command, get_input_url


def _get_sanitized_command(command):
    """ Creates a copy of the command list with credentials redacted for safe logging. """
    sanitized_command = list(command)
    for i, part in enumerate(sanitized_command):
        # Redact user:pass@
        part = re.sub(r"(rtsp://[^:]+:)([^@]+)(@)", r"\1***\3", part)
        # Redact password=... in URL parameters
        part = re.sub(r"(password=)[^&_]+", r"\1***", part)
        sanitized_command[i] = part
    return sanitized_command


def _set_camera_status_error(logger, camera_status, cam_name, message):
    """Sets the camera status to ERROR and logs the error message."""
    camera_status.set(cam_name, "ERROR")
    logger.error(message, exc_info=True, extra={"camera_name": cam_name})


def get_stream_resolution(input_url, logger, cam_name):
    """Gets the resolution of the input stream using ffprobe."""
    command = [
        "ffprobe",
        "-rtsp_transport",
        "tcp",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_streams",
        input_url
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "video":
                    width = stream.get("width")
                    height = stream.get("height")
                    if width and height:
                        resolution = f"{width}x{height}"
                        logger.info(f"Detected resolution: {resolution}", extra={"camera_name": cam_name})
                        return resolution
    except (subprocess.SubprocessError, json.JSONDecodeError, FileNotFoundError) as e:
        logger.error(f"Failed to get stream resolution: {e}", exc_info=True, extra={"camera_name": cam_name})
    return "N/A" # Return N/A on failure


def run_ffmpeg_for_camera(camera_config, logger, camera_status, stop_event, thread_state):
    """A dedicated thread function to manage a single FFmpeg process."""
    cam_name = camera_config["camera"]["name"]
    processing_config = camera_config["camera"].get("processing", {})
    restart_delay = processing_config.get("restart_delay", 15)
    hwaccel_preferred = processing_config.get("hwaccel", True)
    fallback_retry_seconds = 600 # 10 minutes

    while not stop_event.is_set():
        process = None
        try:
            # --- MODIFIED: State is now read from the shared dictionary at the start of each loop ---
            hwaccel_available = thread_state.get("hwaccel_available", True)
            fallback_timestamp = thread_state.get("fallback_timestamp")

            # --- NEW: Logic to re-enable GPU check ---
            if fallback_timestamp and (time.time() - fallback_timestamp) > fallback_retry_seconds:
                logger.info(
                    f"{fallback_retry_seconds / 60:.0f} minutes have passed since falling back to CPU for camera '{cam_name}'."
                    " Attempting to use GPU again.",
                    extra={"camera_name": cam_name}
                )
                thread_state["hwaccel_available"] = True
                thread_state["fallback_timestamp"] = None
                # Update local state for this run
                hwaccel_available = True
                fallback_timestamp = None

            camera_status.set(cam_name, "CONNECTING")
            logger.info(
                f"Incoming stream from rtsp://{camera_config['camera']['ip']}:554...",
                extra={"camera_name": cam_name},
            )
            input_url = get_input_url(camera_config)
            resolution = get_stream_resolution(input_url, logger, cam_name)

            # --- NEW: Modify config for fallback ---
            temp_camera_config = copy.deepcopy(camera_config)
            if 'processing' not in temp_camera_config['camera']:
                temp_camera_config['camera']['processing'] = {}
            
            use_hwaccel_this_run = hwaccel_preferred and hwaccel_available
            temp_camera_config['camera']['processing']['hwaccel'] = use_hwaccel_this_run

            command, details = build_ffmpeg_command(temp_camera_config)
            details["resolution"] = resolution
            if hwaccel_preferred:
                details["hwaccel"] = "Enabled" if use_hwaccel_this_run else "CPU Fallback"
            else:
                details["hwaccel"] = "Disabled"

            summary = (
                f"Processing summary:\n"
                f" ├─ Resolution: {details.get('resolution', 'N/A')}\n"
                f" ├─ HW Accel: {details.get('hwaccel', 'N/A')}\n"
                f" ├─ Video Codec: {details.get('codec', 'N/A')}\n"
                f" ├─ Bitrate: {details.get('bitrate', 'N/A')}\n"
            f" ├─ Splitting: {details.get('splitting', 'Disabled')}\n"
                f" └─ Audio: {details.get('audio', 'N/A')}"
            )
            logger.info(summary, extra={"camera_name": cam_name})
            camera_status.update_details(cam_name, details)

            # Log the sanitized command to avoid exposing credentials
            sanitized_command_str = " ".join(_get_sanitized_command(command))
            logger.info(f"Executing FFmpeg command: {sanitized_command_str}", extra={"camera_name": cam_name})

            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            camera_status.set(cam_name, "ONLINE")
            logger.info(
                f"FFmpeg process started successfully (PID {process.pid}). Publishing to MediaMTX.",
                extra={"camera_name": cam_name},
            )

            while not stop_event.is_set() and process.poll() is None:
                stop_event.wait(0.5)

            if stop_event.is_set():
                logger.info(
                    "Stop signal received, terminating FFmpeg process.",
                    extra={"camera_name": cam_name},
                )
                process.terminate()
                
            stdout, stderr = process.communicate(timeout=10)

            if process.returncode != 0 and not stop_event.is_set():
                error_message = (
                    f"FFmpeg process exited unexpectedly with code {process.returncode}.\n"
                    + f"stdout: {stdout}\n"
                    + f"stderr: {stderr}"
                )
                _set_camera_status_error(
                    logger, camera_status, cam_name, error_message,
                )
                
                # --- MODIFIED: Fallback trigger ---
                is_cuda_error = "cuda" in stderr.lower() or "cuvid" in stderr.lower() or "nvenc" in stderr.lower()
                if use_hwaccel_this_run and is_cuda_error:
                    logger.warning(
                        f"CUDA error detected for camera '{cam_name}'. "
                        f"Falling back to CPU for {fallback_retry_seconds / 60:.0f} minutes.",
                        extra={"camera_name": cam_name}
                    )
                    thread_state["hwaccel_available"] = False
                    hwaccel_available = False
                    thread_state["fallback_timestamp"] = time.time()
                    fallback_timestamp = time.time()
                    continue 
            
            elif not stop_event.is_set():
                # Log when a process exits cleanly but was not stopped by the manager
                logger.warning(
                    f"FFmpeg process for '{cam_name}' exited cleanly (code {process.returncode}) but was not "
                    "explicitly stopped. This may indicate the source stream ended. Restarting process.\n"
                    f" stdout: {stdout.strip()}\n"
                    f" stderr: {stderr.strip()}",
                    extra={"camera_name": cam_name}
                )

        except (subprocess.SubprocessError, IOError) as e:
            if not stop_event.is_set():
                # --- NEW: Enhanced exception logging ---
                stdout_data = ""
                stderr_data = ""
                if isinstance(e, subprocess.TimeoutExpired):
                    # The 'text' parameter to Popen means these are strings
                    stdout_data = e.stdout or ""
                    stderr_data = e.stderr or ""

                error_message = (
                    f"A subprocess error occurred, likely due to a hung ffmpeg process: {e}.\n"
                    f" stdout: {stdout_data}\n"
                    f" stderr: {stderr_data}"
                )
                _set_camera_status_error(
                    logger, camera_status, cam_name, error_message
                )
        except Exception as e:
            if not stop_event.is_set():
                _set_camera_status_error(
                    logger, camera_status, cam_name, f"An unexpected exception occurred: {e}",
                )
        finally:
            if process and process.poll() is None:
                process.kill()
                process.wait()

            camera_status.set(cam_name, "OFFLINE")

            if not stop_event.is_set():
                logger.info(
                    f"Restarting in {restart_delay}s...", extra={"camera_name": cam_name}
                )
                for _ in range(restart_delay * 2):
                    if stop_event.is_set():
                        break
                    stop_event.wait(0.5)

    logger.info(
        "Camera management thread has been stopped.", extra={"camera_name": cam_name}
    )
    camera_status.delete(cam_name)
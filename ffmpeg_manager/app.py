import sys
import yaml
import logging
import threading
import signal
import argparse
import time
import json
from urllib import request, error
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from views import app, init_views
from process_manager import run_ffmpeg_for_camera
from camera_status import CameraStatus


class Application:
    def __init__(self, config_path, state_path="/config/state.json"):
        self.config_path = config_path
        self.state_path = state_path
        self.running_threads = {}
        self.config_lock = threading.Lock()
        self.app_logger = logging.getLogger("FFmpegManager")
        self.observer = Observer()
        self.camera_status = CameraStatus()
        self.state = self.load_state()

    def load_state(self):
        if os.path.exists(self.state_path):
            with open(self.state_path, "r") as f:
                return json.load(f)
        return {}

    def save_state(self):
        with open(self.state_path, "w") as f:
            json.dump(self.state, f, indent=4)

    def update_camera_state(self, cam_name, new_state):
        self.state[cam_name] = new_state
        self.save_state()

    def start_camera_thread(self, camera_config, initial_state=None):
        """Starts and registers a new management thread for a single camera."""
        cam_name = camera_config["camera"]["name"]
        stop_event = threading.Event()

        # If no state is provided, use a default (GPU available)
        if initial_state is None:
            initial_state = self.state.get(cam_name, {
                "hwaccel_available": True,
                "fallback_timestamp": None,
            })

        thread = threading.Thread(
            target=run_ffmpeg_for_camera,
            args=(self, camera_config, self.app_logger, self.camera_status, stop_event, initial_state),
            daemon=True,
        )
        thread.start()
        self.running_threads[cam_name] = {
            "thread": thread,
            "stop_event": stop_event,
            "config": camera_config,
            "state": initial_state, # Store the state here
        }
        self.state[cam_name] = initial_state
        self.save_state()
        self.app_logger.info(
            f"Management thread for '{cam_name}' started.", extra={"camera_name": cam_name}
        )

    def stop_camera_thread(self, cam_name):
        """Stops and unregisters a camera thread."""
        if cam_name in self.running_threads:
            self.app_logger.info(
                f"Stopping management thread for '{cam_name}'...",
                extra={"camera_name": "general"},
            )
            self.running_threads[cam_name]["stop_event"].set()
            self.running_threads[cam_name]["thread"].join(timeout=15)
            del self.running_threads[cam_name]
            if cam_name in self.state:
                del self.state[cam_name]
                self.save_state()
            self.camera_status.delete(cam_name)
            self.app_logger.info(
                f"Thread for '{cam_name}' stopped.", extra={"camera_name": "general"}
            )

    def restart_camera_thread(self, cam_name):
        """Restarts a specific camera thread via API request."""
        if cam_name in self.running_threads:
            self.app_logger.info(
                f"Restarting camera thread for '{cam_name}' via API.",
                extra={"camera_name": cam_name},
            )
            thread_info = self.running_threads[cam_name]
            self.stop_camera_thread(cam_name)
            self.start_camera_thread(thread_info["config"], thread_info["state"])
            return True

        self.app_logger.warning(
            f"Attempted to restart non-existent camera '{cam_name}'.",
            extra={"camera_name": "general"},
        )
        return False

    def update_camera_threads(self):
        """Compares running threads with the latest config and starts/stops/restarts as needed."""
        with self.config_lock:
            self.app_logger.info(
                "Checking configuration and updating camera threads...",
                extra={"camera_name": "general"},
            )
            try:
                with open(self.config_path, "r") as f:
                    config = yaml.safe_load(f)
                new_cameras = {
                    cam["camera"]["name"]: cam for cam in config.get("cameras", [])
                }
            except (IOError, yaml.YAMLError) as e:
                self.app_logger.error(
                    f"Error loading config file: {e}", extra={"camera_name": "general"}
                )
                return

            running_cam_names = set(self.running_threads.keys())
            new_cam_names = set(new_cameras.keys())

            # Stop threads for removed cameras
            for cam_name in running_cam_names - new_cam_names:
                self.stop_camera_thread(cam_name)

            # Start or restart threads for new or changed cameras
            for cam_name, cam_config in new_cameras.items():
                if cam_name not in running_cam_names:
                    self.app_logger.info(
                        f"New camera '{cam_name}' found. Starting...",
                        extra={"camera_name": cam_name},
                    )
                    self.start_camera_thread(cam_config)
                elif cam_config != self.running_threads[cam_name]["config"]:
                    self.app_logger.info(
                        f"Config for '{cam_name}' changed. Restarting...",
                        extra={"camera_name": cam_name},
                    )
                    self.stop_camera_thread(cam_name)
                    self.start_camera_thread(cam_config) # Start with fresh state on config change

    def poll_mediamtx_api(self):
        """Periodically polls the MediaMTX API to get stream details."""
        while True:
            try:
                with request.urlopen("http://mediamtx:9997/v2/paths/list", timeout=5) as response:
                    if response.status == 200:
                        data = json.loads(response.read())
                        if 'items' in data:
                            all_paths = {item['name']: item for item in data['items']}
                            
                            with self.config_lock:
                                running_cams = list(self.running_threads.keys())
                                
                            for cam_name in running_cams:
                                details = {
                                    'resolution': '',
                                    'bitrate': 0
                                }
                                # Check main stream and split parts
                                for suffix in ['', '_part1', '_part2']:
                                    path_name = f"{cam_name}{suffix}"
                                    if path_name in all_paths:
                                        path_data = all_paths[path_name]
                                        if 'medias' in path_data and path_data['medias']:
                                            for media in path_data['medias']:
                                                if media['type'] == 'video':
                                                    if 'width' in media and 'height' in media:
                                                        details['resolution'] = f"{media['width']}x{media['height']}"
                                                    if 'bytesPerSecond' in path_data:
                                                        details['bitrate'] = round(path_data['bytesPerSecond'] * 8 / 1000)
                                                    break # Found video, stop checking medias
                                        break # Found a matching path, stop checking suffixes
                                self.camera_status.update_details(cam_name, details)
                                
            except (error.URLError, json.JSONDecodeError, ConnectionResetError) as e:
                self.app_logger.debug(f"Could not connect to MediaMTX API: {e}", extra={"camera_name": "general"})
            except Exception as e:
                self.app_logger.error(f"Unexpected error in MediaMTX poller: {e}", extra={"camera_name": "general"})

            time.sleep(10)

    def shutdown_handler(self, signum, frame):
        """Gracefully shut down the application."""
        self.app_logger.warning(
            "Shutdown signal received. Stopping all threads...",
            extra={"camera_name": "general"},
        )
        self.save_state()
        self.observer.stop()
        for cam_name in list(self.running_threads.keys()):
            self.stop_camera_thread(cam_name)
        self.observer.join()
        sys.exit(0)

    def run(self):
        # --- Logger Setup ---
        self.app_logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - [%(camera_name)s] - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        if self.app_logger.hasHandlers():
            self.app_logger.handlers.clear()
        self.app_logger.addHandler(handler)

        # --- Startup Banner ---
        self.app_logger.info(
            "========================================", extra={"camera_name": "general"}
        )
        self.app_logger.info(
            " 🎥 FFmpeg Camera Manager - Starting Up ", extra={"camera_name": "general"}
        )
        self.app_logger.info(
            "========================================", extra={"camera_name": "general"}
        )

        # --- System Setup ---
        init_views(self.camera_status, self)
        signal.signal(signal.SIGINT, self.shutdown_handler)
        signal.signal(signal.SIGTERM, self.shutdown_handler)

        self.update_camera_threads()

        event_handler = ConfigChangeHandler(self)
        self.observer.schedule(event_handler, self.config_path, recursive=False)
        self.observer.start()
        self.app_logger.info(
            "✅ Started configuration file watcher.", extra={"camera_name": "general"}
        )

        # --- Start MediaMTX Poller ---
        poller_thread = threading.Thread(target=self.poll_mediamtx_api, daemon=True)
        poller_thread.start()
        self.app_logger.info(
            "✅ Started MediaMTX API poller.", extra={"camera_name": "general"}
        )
        
        # --- Start Web Server and Log URL ---
        # The host port is mapped from 18890 in docker-compose.yaml
        HOST_PORT = 18890
        self.app_logger.info(f"🚀 Starting web server...", extra={"camera_name": "general"})
        self.app_logger.info(
            f"✅ Web UI is now ONLINE at: http://<your_server_ip>:{HOST_PORT}",
            extra={"camera_name": "general"},
        )
        
        # Silence the default Flask/Werkzeug logger to keep our logs clean
        log = logging.getLogger("werkzeug")
        log.setLevel(logging.ERROR)
        
        app.run(host="0.0.0.0", port=8080)


class ConfigChangeHandler(FileSystemEventHandler):
    def __init__(self, app):
        self.app = app

    def on_modified(self, event):
        if not event.is_directory and event.src_path.endswith("/cameras.yaml"):
            self.app_logger.info(
                "cameras.yaml modified. Reloading.", extra={"camera_name": "general"}
            )
            self.app.update_camera_threads()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FFmpeg Camera Manager")
    parser.add_argument(
        "--config",
        default="/config/cameras.yaml",
        help="Path to the cameras configuration file.",
    )
    parser.add_argument(
        "--state",
        default="/config/state.json",
        help="Path to the state file.",
    )
    args = parser.parse_args()

    main_app = Application(args.config, args.state)
    main_app.run()
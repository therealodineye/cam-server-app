import threading

class CameraStatus:
    """A thread-safe class to store and manage the status of each camera."""

    def __init__(self):
        self._statuses = {}
        self._lock = threading.Lock()

    def get(self, camera_name):
        """Get the status of a specific camera."""
        with self._lock:
            return self._statuses.get(camera_name, {"status": "UNKNOWN"})

    def set(self, camera_name, status):
        """Set the status of a specific camera."""
        with self._lock:
            if camera_name not in self._statuses:
                self._statuses[camera_name] = {}
            self._statuses[camera_name]['status'] = status

    def update_details(self, camera_name, details):
        """Update the details of a specific camera (e.g., resolution, bitrate)."""
        with self._lock:
            if camera_name not in self._statuses:
                self._statuses[camera_name] = {}
            self._statuses[camera_name].update(details)

    def delete(self, camera_name):
        """Remove a camera from the status tracking."""
        with self._lock:
            if camera_name in self._statuses:
                del self._statuses[camera_name]

    def get_all(self):
        """Get a copy of all camera statuses."""
        with self._lock:
            return self._statuses.copy()
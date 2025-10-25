# 🎥 Dual lens IP cam splitter

A Docker-based application for managing and processing multiple RTSP camera streams. This app was primarily built to split single streams from dual-lens cameras into two separate streams, making them usable as two different cameras in NVR systems like iSpyAgentDVR.

It also provides an optional feature to convert H.265 streams to H.264, which can be useful for NVR systems and browsers that have trouble with H.265.

## ✨ Features

*   **Dual-Lens Camera Splitting**: Splits a single RTSP stream into two separate streams (e.g., top/bottom or left/right).
*   **H.265 to H.264 Conversion**: Optional on-the-fly transcoding for improved compatibility.
*   **NVIDIA Hardware Acceleration**: Utilizes NVENC/NVDEC for efficient transcoding.
*   **Dynamic Configuration**: Add or modify cameras by editing a YAML file.
*   **Resilient**: Automatically restarts failed FFmpeg processes.

## 🚀 Getting Started

### 1. Configure Your Cameras

Copy `config/cameras.yaml.example` to `config/cameras.yaml` and edit it with your camera's IP address, RTSP path, and credentials.

### 2. Launch the Application

```bash
docker-compose up --build -d
```

## ⚙️ Usage

To add or modify a camera, edit `config/cameras.yaml` and restart the manager:

```bash
docker-compose restart ffmpeg-manager
```

The processed streams will be available at:

*   `rtsp://<your_server_ip>:18554/<camera_name>_part1`
*   `rtsp://<your_server_ip>:18554/<camera_name>_part2`

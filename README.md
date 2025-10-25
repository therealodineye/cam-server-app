<h1>🎥 FFmpeg Camera Stream Manager</h1>
<p>
    <img src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker">
    <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
    <img src="https://img.shields.io/badge/FFmpeg-007800?style=for-the-badge&logo=ffmpeg&logoColor=white" alt="FFmpeg">
</p>

<p>A flexible, Docker-based application for managing and processing multiple RTSP camera streams. This manager uses a Python script to dynamically launch and monitor FFmpeg processes based on a simple YAML configuration, enabling features like hardware-accelerated transcoding, video splitting, and audio manipulation.</p>

<h2>✨ Features</h2>
<ul>
    <li><strong>Dynamic Configuration</strong>: Add, remove, or modify camera streams by simply editing a <code>cameras.yaml</code> file. No need to change the Docker Compose file for each camera.</li>
    <li><strong>NVIDIA Hardware Acceleration</strong>: Utilizes NVIDIA's NVENC/NVDEC for efficient, low-CPU transcoding of H.264 and H.265 (HEVC) streams.</li>
    <li><strong>Stream Manipulation</strong>:
        <ul>
            <li>Split a single camera feed into multiple outputs (e.g., top/bottom or left/right).</li>
            <li>Transcode between video codecs (e.g., H.265 to H.264 for wider compatibility).</li>
            <li>Full control over audio streams (enable, disable, or assign to specific splits).</li>
        </ul>
    </li>
    <li><strong>Centralized Management</strong>: A single container manages all FFmpeg processes, simplifying deployment and monitoring.</li>
    <li><strong>Structured Logging</strong>: Generates clean, JSON-formatted logs for easy integration with log management systems like Graylog.</li>
    <li><strong>Resilient</strong>: Automatically restarts any FFmpeg process that fails or disconnects.</li>
</ul>

<h2>🛠️ Technology Stack</h2>
<ul>
    <li><strong>Docker & Docker Compose</strong>: For containerizing the application and its dependencies.</li>
    <li><strong>Python</strong>: The core management script that reads the configuration and controls FFmpeg.</li>
    <li><strong>FFmpeg</strong>: The workhorse for all video and audio processing.</li>
    <li><strong>MediaMTX</strong>: (Formerly RTSP-Simple-Server) A ready-to-use, zero-dependency RTSP/RTMP/HLS server for re-broadcasting the processed streams.</li>
</ul>

<h2>📋 Prerequisites</h2>
<ul>
    <li>A Linux server with Docker and Docker Compose installed.</li>
    <li>An NVIDIA GPU with the appropriate drivers installed on the host machine.</li>
    <li>The NVIDIA Container Toolkit installed to enable GPU access within Docker containers.</li>
</ul>

<h2>🚀 Getting Started</h2>
<h3>1. Clone the Repository</h3>
<p>Clone this repository to your server:</p>
<pre><code>git clone &lt;your-repository-url&gt;
cd cam-server-app
</code></pre>

<h3>2. Configure Your Cameras</h3>
<p>The entire configuration is managed in the <code>config/</code> directory.</p>
<ul>
    <li><strong>Create your personal config</strong>: Copy the provided example file.
        <pre><code>cp config/cameras.yaml.example config/cameras.yaml</code></pre>
    </li>
    <li><strong>Edit <code>config/cameras.yaml</code></strong>: Open the file and enter the real IP addresses, RTSP paths, usernames, and passwords for your cameras. Adjust the processing options for each camera as needed. The <code>cameras.yaml</code> file is ignored by Git, so your credentials will remain private.</li>
</ul>

<h3>3. Launch the Application</h3>
<p>Run the following command from the root of the project directory:</p>
<pre><code>docker-compose up --build -d
</code></pre>
<ul>
    <li><code>--build</code>: Only needed the first time you run it or after changing the Python application code.</li>
    <li><code>-d</code>: Runs the containers in the background.</li>
</ul>

<h2>⚙️ Usage</h2>
<h3>Adding/Modifying Cameras</h3>
<p>To add a new camera or change an existing one, simply edit the <code>config/cameras.yaml</code> file and then restart the manager to apply the changes:</p>
<pre><code>docker-compose restart ffmpeg-manager
</code></pre>

<h3>Viewing Logs</h3>
<p>To monitor the application and see the status of your camera streams, use this command:</p>
<pre><code>docker-compose logs -f ffmpeg-manager
</code></pre>

<h3>Accessing Streams</h3>
<p>The processed streams will be available via MediaMTX. For a camera named <code>driveway-cam</code> that has been split, the streams would be:</p>
<ul>
    <li><code>rtsp://&lt;your_server_ip&gt;:18554/driveway-cam_part1</code></li>
    <li><code>rtsp://&lt;your_server_ip&gt;:18554/driveway-cam_part2</code></li>
</ul>

<h2>📄 License</h2>
<p>This project is licensed under the MIT License. See the <code>LICENSE</code> file for details.</p>
```

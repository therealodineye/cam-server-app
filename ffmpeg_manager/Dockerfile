# Use the FFmpeg 8 image with NVIDIA support as our base
FROM jrottenberg/ffmpeg:8-nvidia

# Install Python, pip, and the 'venv' module all in one go
RUN apt-get update && apt-get install -y python3 python3-pip python3-venv && rm -rf /var/lib/apt/lists/*

# Set the working directory for the application
WORKDIR /app

# Create a virtual environment
RUN python3 -m venv /opt/venv

# Set the PATH environment variable to use the venv's executables
ENV PATH="/opt/venv/bin:${PATH}"

# Copy and install requirements first to leverage Docker's build cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Override the base image's default entrypoint to run Python
ENTRYPOINT ["python"]

# Specify the script to run
CMD ["app.py"]
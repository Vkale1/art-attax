FROM python:3.12-slim

WORKDIR /app

# System dependencies
# libgl1 and libglu1-mesa needed by py5 for rendering
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    g++ \
    libgl1 \
    libglu1-mesa \
    libgomp1 \
    xvfb \
    default-jdk \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Data and output directories (will be mounted as volumes)
RUN mkdir -p /data /outputs

CMD ["python", "main.py"]

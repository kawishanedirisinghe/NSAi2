# Multi-stage Docker build for OpenManus AI Platform
FROM python:3.11-slim as base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    TZ=UTC

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    wget \
    gnupg2 \
    software-properties-common \
    apt-transport-https \
    ca-certificates \
    lsb-release \
    && rm -rf /var/lib/apt/lists/*

# Install NVIDIA Docker support (optional for GPU)
RUN curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg \
    && curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    tee /etc/apt/sources.list.d/nvidia-container-toolkit.list \
    && apt-get update || true

# Create non-root user
RUN groupadd -r openmanus && useradd -r -g openmanus -m -s /bin/bash openmanus

# Set working directory
WORKDIR /app

# Copy requirements first (for better caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Production stage
FROM base as production

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p workspace uploads logs && \
    chown -R openmanus:openmanus /app

# Switch to non-root user
USER openmanus

# Expose ports
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:5000/api/system/health || exit 1

# Default command
CMD ["python", "main.py"]

# Development stage
FROM base as development

# Install development dependencies
RUN pip install --no-cache-dir pytest pytest-asyncio black flake8 mypy

# Copy application code
COPY . .

# Create directories and set permissions
RUN mkdir -p workspace uploads logs && \
    chown -R openmanus:openmanus /app

# Switch to non-root user
USER openmanus

# Expose ports (including debug port)
EXPOSE 5000 5678

# Development command
CMD ["python", "-m", "flask", "run", "--host=0.0.0.0", "--port=5000", "--debug"]
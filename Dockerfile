# TAOLIE Host Agent Docker Image
FROM ubuntu:22.04

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    postgresql-client \
    curl \
    wget \
    gnupg \
    lsb-release \
    ca-certificates \
    software-properties-common \
    && rm -rf /var/lib/apt/lists/*

# Install Docker
RUN curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null \
    && apt-get update \
    && apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/*

# Create application user
RUN useradd -m -s /bin/bash taolie-agent

# Create application directories
RUN mkdir -p /etc/taolie-host-agent \
    && mkdir -p /var/log/taolie-host-agent \
    && mkdir -p /var/lib/taolie-host-agent \
    && chown -R taolie-agent:taolie-agent /etc/taolie-host-agent \
    && chown -R taolie-agent:taolie-agent /var/log/taolie-host-agent \
    && chown -R taolie-agent:taolie-agent /var/lib/taolie-host-agent

# Set working directory
WORKDIR /var/lib/taolie-host-agent

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application code
COPY agent/ ./agent/
COPY config.yaml /etc/taolie-host-agent/config.yaml

# Set proper permissions
RUN chown -R taolie-agent:taolie-agent /var/lib/taolie-host-agent

# Switch to application user
USER taolie-agent

# Expose ports (these will be mapped by the host)
EXPOSE 2222 8888 9999

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 -c "import sys; sys.exit(0)" || exit 1

# Set entrypoint
ENTRYPOINT ["python3", "-m", "agent.main"]
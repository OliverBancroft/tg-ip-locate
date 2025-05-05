FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    nmap \
    mtr \
    curl \
    iputils-ping \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Make start script executable
RUN chmod +x start.sh

# Create a modified start script that handles permissions
RUN mv start.sh original_start.sh && \
    echo '#!/bin/bash' > start.sh && \
    echo 'set -e' >> start.sh && \
    echo 'mkdir -p /app/data' >> start.sh && \
    echo 'chmod -R 777 /app/data' >> start.sh && \
    echo 'exec ./original_start.sh' >> start.sh && \
    chmod +x start.sh

# Create data directory
RUN mkdir -p /app/data && chmod 777 /app/data

# Do NOT switch to a non-root user in the Dockerfile
# This will allow the container to fix permissions at runtime

# Expose port
EXPOSE 8080

# Set environment variables
ENV LOCATION=SG
ENV PYTHONUNBUFFERED=1
ENV FLASK_ENV=production
ENV FLASK_APP=server.py
ENV GUNICORN_WORKERS=1
ENV GUNICORN_THREADS=1
ENV GUNICORN_TIMEOUT=120

# Run the application
CMD ["./start.sh"]
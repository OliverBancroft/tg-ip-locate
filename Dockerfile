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

# Create a non-root user with explicit UID/GID
RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -m appuser && \
    mkdir -p /app/data && \
    chown -R appuser:appgroup /app && \
    chmod -R 755 /app && \
    chmod 777 /app/data

# Make start script executable
RUN chmod +x start.sh

# Switch to non-root user
USER appuser

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
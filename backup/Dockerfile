# Multi-stage build for shiori-backup
# Stage 1: Build - Download rclone binary
FROM alpine:3.21 AS builder

# Install dependencies for downloading and extracting rclone
RUN apk add --no-cache curl unzip

# Detect architecture and download appropriate rclone binary
RUN ARCH=$(uname -m) && \
    case "$ARCH" in \
        x86_64) RCLONE_ARCH="amd64" ;; \
        aarch64) RCLONE_ARCH="arm64" ;; \
        armv7l) RCLONE_ARCH="arm-v7" ;; \
        armv6l) RCLONE_ARCH="arm-v6" ;; \
        *) echo "Unsupported architecture: $ARCH" && exit 1 ;; \
    esac && \
    echo "Downloading rclone for $RCLONE_ARCH" && \
    curl -sL "https://downloads.rclone.org/rclone-current-linux-${RCLONE_ARCH}.zip" -o /tmp/rclone.zip && \
    unzip /tmp/rclone.zip -d /tmp && \
    mv /tmp/rclone-*-linux-${RCLONE_ARCH}/rclone /tmp/rclone && \
    chmod +x /tmp/rclone

# Stage 2: Final image
FROM python:3.12-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    sqlite3 \
    gnupg \
    postgresql-client \
    default-mysql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy rclone binary from builder stage
COPY --from=builder /tmp/rclone /usr/local/bin/rclone

# Create necessary directories
RUN mkdir -p /app /backups /config/rclone /shiori-data

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ .

# Run backup script by default
CMD ["python", "-u", "backup.py"]

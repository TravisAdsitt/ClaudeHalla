FROM python:3.11-slim

WORKDIR /app

# Install system deps for ldap3 (libldap, libsasl2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libldap-2.5-0 \
    libsasl2-2 \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml ./
COPY src/ ./src/
COPY config.yaml ./

# Install Python dependencies
RUN pip install --no-cache-dir -e .

# Data directory (mounted as PVC in OKD)
RUN mkdir -p /data

EXPOSE 8080

ENV CLAUDE_HALLA_CONFIG=/app/config.yaml

CMD ["claude-halla"]

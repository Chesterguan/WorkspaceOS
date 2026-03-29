FROM python:3.11-slim

# Install system deps needed by asyncpg (C extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer cache friendly)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the backend source
COPY . .

# CMD is intentionally omitted — docker-compose provides the command
# so we can run migrations before starting the server.

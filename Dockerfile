FROM python:3.11-slim

# Keep Python lean and unbuffered for real-time logs.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first to leverage Docker layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application source.
COPY app ./app
COPY sql ./sql
COPY pyproject.toml ./

# Raw JSON output directory (also a mounted volume in docker-compose).
RUN mkdir -p /app/data

# Default to showing the CLI help; override with `docker compose run app ...`.
ENTRYPOINT ["python", "-m", "app"]
CMD ["--help"]

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1

WORKDIR /app

# Add ca-certificates so HTTPS requests work, plus build-essential for asyncpg
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates build-essential \
 && update-ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt uvicorn[standard]

COPY . .

# Show env and start with full debug logs
CMD ["/bin/sh","-lc","echo '📦 /app:' && ls -la && echo '🔧 ENV:' && env | sort && echo '🚀 Starting…' && python -X dev -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080} --log-level debug"]

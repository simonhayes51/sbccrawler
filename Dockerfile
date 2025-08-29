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
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Expose the port Railway expects
EXPOSE $PORT

# Start command that works with Railway
CMD uvicorn main:app --host 0.0.0.0 --port $PORT

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1

WORKDIR /app

RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# add uvicorn[standard] for clearer logs + watchdogs
RUN pip install --no-cache-dir -r requirements.txt uvicorn[standard]

COPY . .

# Show what the container sees, then start uvicorn in debug
CMD ["/bin/sh","-lc","echo '📦 /app:' && ls -la && echo '🔧 ENV:' && env | sort && echo '🚀 Starting…' && python -X dev -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080} --log-level debug --reload-dir /app"]

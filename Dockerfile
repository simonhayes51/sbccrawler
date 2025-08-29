FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    build-essential \
    curl \
 && update-ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN echo "📦 Installing Python packages..." && \
    pip install --no-cache-dir -r requirements.txt && \
    echo "✅ Python packages installed"

# Copy application code
COPY . .

# Debug: Show what files we have
RUN echo "📁 Files in /app:" && ls -la

# Debug: Test Python imports
RUN echo "🐍 Testing Python imports..." && \
    python -c "import fastapi; print('✅ FastAPI imported')" && \
    python -c "import uvicorn; print('✅ Uvicorn imported')" && \
    python -c "import main; print('✅ Main module imported')" || echo "❌ Main import failed"

# Expose port
EXPOSE $PORT

# Debug startup command
CMD echo "🚀 Starting Railway deployment..." && \
    echo "📋 Environment variables:" && \
    echo "PORT: $PORT" && \
    echo "RAILWAY_ENVIRONMENT: $RAILWAY_ENVIRONMENT" && \
    echo "DATABASE_URL set: $([ -n "$DATABASE_URL" ] && echo 'Yes' || echo 'No')" && \
    echo "🐍 Python version: $(python --version)" && \
    echo "📦 FastAPI version: $(python -c 'import fastapi; print(fastapi.__version__)')" && \
    echo "🌐 Starting uvicorn on 0.0.0.0:$PORT..." && \
    uvicorn main:app --host 0.0.0.0 --port $PORT --log-level info

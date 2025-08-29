#!/bin/bash
echo "🚀 Starting FUT SBC Tracker with Nixpacks..."
echo "📋 PORT: $PORT"
echo "🔗 DATABASE_URL configured: $([ -n "$DATABASE_URL" ] && echo 'Yes' || echo 'No')"

# Start with uvicorn
exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080} --log-level info

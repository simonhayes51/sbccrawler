#!/usr/bin/env python3

# Ultra-minimal FastAPI app for Railway debugging
import os
import sys

print("🚀 Python starting...")
print(f"🐍 Python version: {sys.version}")
print(f"📂 Working directory: {os.getcwd()}")
print(f"🌐 PORT environment: {os.getenv('PORT', 'NOT SET')}")

try:
    from fastapi import FastAPI
    print("✅ FastAPI imported successfully")
except ImportError as e:
    print(f"❌ FastAPI import failed: {e}")
    sys.exit(1)

try:
    from fastapi.responses import JSONResponse
    print("✅ FastAPI responses imported")
except ImportError as e:
    print(f"❌ FastAPI responses import failed: {e}")

# Create the FastAPI app
app = FastAPI(
    title="Railway Debug App",
    description="Testing Railway deployment",
    version="1.0.0"
)

@app.get("/")
async def root():
    return {
        "message": "🎉 FastAPI is working on Railway!",
        "status": "success",
        "port": os.getenv("PORT", "unknown"),
        "python_version": sys.version,
        "working_dir": os.getcwd()
    }

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "railway-debug"}

@app.get("/env")
async def env_info():
    return {
        "PORT": os.getenv("PORT"),
        "RAILWAY_ENVIRONMENT": os.getenv("RAILWAY_ENVIRONMENT"),
        "DATABASE_URL_SET": bool(os.getenv("DATABASE_URL")),
        "PWD": os.getenv("PWD"),
        "HOME": os.getenv("HOME")
    }

print("✅ FastAPI app created successfully")

# For local testing
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    print(f"🚀 Starting uvicorn on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

# main.py - Minimal version for debugging
import os
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="FUT SBC Tracker - Debug Mode")

@app.get("/health")
async def health():
    return {
        "status": "ok", 
        "port": os.getenv("PORT", "8080"),
        "database_url_set": bool(os.getenv("DATABASE_URL")),
        "message": "App is running!"
    }

@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>FUT SBC Tracker - Debug</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; background: #f0f0f0; }
            .container { max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            h1 { color: #2c3e50; text-align: center; }
            .status { background: #e8f5e8; padding: 15px; border-radius: 5px; margin: 20px 0; }
            .info { background: #f8f9fa; padding: 10px; border-radius: 5px; font-family: monospace; font-size: 14px; }
            a { color: #3498db; text-decoration: none; }
            a:hover { text-decoration: underline; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🚀 FUT SBC Tracker</h1>
            <div class="status">
                <strong>✅ App is running successfully!</strong>
            </div>
            
            <p>This is a minimal version to test Railway deployment.</p>
            
            <div class="info">
                <strong>Environment:</strong><br>
                PORT: """ + os.getenv("PORT", "8080") + """<br>
                DATABASE_URL: """ + ("✅ Set" if os.getenv("DATABASE_URL") else "❌ Not set") + """
            </div>
            
            <h3>Available Endpoints:</h3>
            <ul>
                <li><a href="/health">/health</a> - Health check</li>
                <li><a href="/test">/test</a> - Simple test</li>
            </ul>
            
            <p><em>Once this works, we can add back the full SBC functionality!</em></p>
        </div>
    </body>
    </html>
    """)

@app.get("/test")
async def test():
    return {"message": "Test endpoint working!", "status": "success"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    print(f"🚀 Starting app on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)

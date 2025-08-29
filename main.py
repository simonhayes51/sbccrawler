# main.py
import os
import asyncio
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from scheduler import schedule_loop, run_job
from db import init_db, get_all_sets
try:
    from db import get_set_by_slug  # optional
except Exception:
    get_set_by_slug = None

app = FastAPI(title="SBC Crawler API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],    # tighten later if needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

HEALTH = {
    "status": "ok",
    "ready": False,
    "last_run": None,
    "startup_error": None,
    "database_configured": bool(os.getenv("DATABASE_URL")),
}

UI_HTML = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>SBC Crawler</title>
<style>
:root { --bg:#0b0b0f; --card:#151521; --text:#e7e7ee; --muted:#9aa0a6; --accent:#00ff80; }
*{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 system-ui,Segoe UI,Roboto,Arial}
header{padding:16px 20px;border-bottom:1px solid #222} h1{margin:0;font-size:18px}
.container{max-width:1100px;margin:24px auto;padding:0 16px}
.toolbar{display:flex;gap:10px;align-items:center;margin-bottom:16px}
button{background:var(--accent);color:#000;border:0;padding:10px 14px;border-radius:10px;font-weight:700;cursor:pointer}
button:disabled{opacity:.6;cursor:default}
.status{color:var(--muted);font-size:12px;margin-left:auto}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px}
.card{background:var(--card);border:1px solid #26263a;border-radius:14px;padding:14px;display:flex;flex-direction:column;gap:8px}
.name{font-weight:700}
.meta{color:var(--muted);font-size:12px}
.pill{display:inline-block;background:#1f1f2e;color:var(--muted);padding:3px 8px;border-radius:999px;font-size:12px;margin-right:6px}
.empty{color:var(--muted);text-align:center;padding:40px 0;border:1px dashed #2a2a3d;border-radius:14px}
a{color:var(--accent);text-decoration:none}
.list{margin-top:8px}
.req{color:#cfd3ff;font-size:12px;margin:2px 0}
</style>
</head><body>
<header><h1>🧩 SBC Crawler</h1></header>
<div class="container">
  <div class="toolbar">
    <button id="crawlBtn">Run Crawl Now</button>
    <div class="status" id="status">Loading…</div>
  </div>
  <div id="content"></div>
</div>
<script>
async function getJSON(url, opts={}) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
function el(tag, attrs={}, ...children) {
  const e = document.createElement(tag);
  for (const [k,v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else if (k.startsWith("on") && typeof v === "function") e.addEventListener(k.slice(2).toLowerCase(), v);
    else e.setAttribute(k, v);
  }
  for (const c of children) e.append(c instanceof Node ? c : document.createTextNode(c));
  return e;
}
async function load() {
  const status = document.getElementById("status");
  const content = document.getElementById("content");
  content.innerHTML = "";
  status.textContent = "Loading…";
  try {
    const health = await getJSON("/api/health");
    const data = await getJSON("/api/sbcs");
    status.textContent = `ready: ${health.ready} | last_run: ${health.last_run || "—"}`;
    if (!data.count) {
      content.append(el("div",{class:"empty"},"No SBCs found yet. Click “Run Crawl Now”."));
      return;
    }
    const grid = el("div",{class:"grid"});
    for (const row of data.sets) {
      const chCount = Array.isArray(row.challenges) ? row.challenges.length : 0;
      const card = el("div",{class:"card"},
        el("div",{class:"name"}, row.name || "Untitled"),
        el("div",{class:"meta"},
          el("span",{class:"pill"}, row.repeatable ? "Repeatable" : "One-time"),
          el("span",{class:"pill"}, row.expires_at ? ("Expires " + new Date(row.expires_at).toLocaleDateString()) : "No expiry")
        ),
        row.url ? el("a",{href:row.url,target:"_blank",rel:"noopener"},"Open on FUT.GG →") : el("div"),
        el("div",{class:"meta"},"Challenges: " + chCount),
        (()=>{const list=el("div",{class:"list"});try{
          const ch=Array.isArray(row.challenges)?row.challenges.slice(0,3):[];
          ch.forEach(c=>list.append(el("div",{class:"req"},"— "+(c?.name||"Challenge")+" ("+(Array.isArray(c?.requirements)?c.requirements.length:0)+" reqs)")));
        }catch{} return list;})()
      );
      grid.append(card);
    }
    content.append(grid);
  } catch (e) {
    status.textContent = "Error loading data";
    content.append(el("div",{class:"empty"},"Failed to load data: " + e.message));
  }
}
document.getElementById("crawlBtn").addEventListener("click", async (e) => {
  const btn = e.currentTarget;
  const status = document.getElementById("status");
  btn.disabled = true; status.textContent = "Crawling…";
  try { await getJSON("/api/debug/trigger-crawl",{method:"POST"}); await load(); }
  catch(e2){ status.textContent="Crawl failed: "+e2.message; }
  finally{ btn.disabled=false; }
});
load();
</script>
</body></html>
"""

@app.on_event("startup")
async def on_startup():
    try:
        await init_db()
        async def initial():
            try:
                HEALTH["last_run"] = "startup"
                await run_job()
                HEALTH["ready"] = True
            except Exception as e:
                HEALTH["startup_error"] = f"{type(e).__name__}: {e}"
                HEALTH["status"] = "error"
                HEALTH["ready"] = False
        asyncio.create_task(initial())
        asyncio.create_task(schedule_loop())
    except Exception as e:
        HEALTH["startup_error"] = f"{type(e).__name__}: {e}"
        HEALTH["status"] = "error"
        HEALTH["ready"] = False

@app.get("/", response_class=HTMLResponse)
async def ui_root():
    return HTMLResponse(content=UI_HTML)

@app.get("/api/health")
async def api_health():
    return {
        "status": HEALTH["status"],
        "ready": HEALTH["ready"],
        "last_run": HEALTH["last_run"],
        "startup_error": HEALTH["startup_error"],
        "database_configured": HEALTH["database_configured"],
    }

@app.post("/api/debug/trigger-crawl")
async def trigger_crawl():
    try:
        await run_job()
        HEALTH["last_run"] = datetime.now(timezone.utc).isoformat()
        HEALTH["ready"] = True
        return {"ok": True, "message": "Manual crawl completed"}
    except Exception as e:
        HEALTH["status"] = "error"
        HEALTH["startup_error"] = f"{type(e).__name__}: {e}"
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sbcs")
async def list_sbcs():
    sets = await get_all_sets()
    return {"count": len(sets), "sets": sets}

@app.get("/api/sbc/{slug}")
async def get_sbc(slug: str):
    if not callable(get_set_by_slug):
        raise HTTPException(status_code=404, detail="Endpoint not available")
    row = await get_set_by_slug(slug)
    if not row:
        raise HTTPException(status_code=404, detail="SBC not found")
    return row

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8080")), log_level="info", reload=False)

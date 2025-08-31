from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
import os
import asyncio

app = FastAPI(title="FUT SBC Tracker")

@app.get("/")
def root():
    return HTMLResponse("""
<!DOCTYPE html>
<html>
<head>
    <title>FUT SBC Debug</title>
    <script src="https://unpkg.com/vue@3/dist/vue.global.prod.js"></script>
    <script src="https://unpkg.com/axios/dist/axios.min.js"></script>
    <style>
        body { font-family: system-ui; margin: 20px; background: #f0f2f5; }
        .container { max-width: 800px; margin: 0 auto; }
        .card { background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        h1 { color: #333; margin-bottom: 20px; }
        button { padding: 10px 20px; background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; margin: 5px; }
        button:disabled { opacity: 0.6; cursor: not-allowed; }
        .log { background: #f8f9fa; padding: 10px; border-radius: 4px; font-family: monospace; font-size: 12px; white-space: pre-wrap; max-height: 400px; overflow-y: auto; }
        .error { background: #f8d7da; color: #721c24; }
        .success { background: #d4edda; color: #155724; }
        .warning { background: #fff3cd; color: #856404; }
        .highlight { background: #e8f5e8; padding: 5px; border-radius: 3px; margin: 5px 0; }
    </style>
</head>
<body>
    <div id="app">
        <div class="container">
            <h1>🔧 FUT SBC Debug Tool</h1>
            
            <div class="card">
                <h3>Step 1: Test Basic Connectivity</h3>
                <button @click="testConnectivity" :disabled="loading">Test fut.gg Connection</button>
                <div v-if="connectivityResult" class="log" :class="connectivityResult.success ? 'success' : 'error'">
                    {{ connectivityResult.message }}
                    <div v-if="connectivityResult.success">
                        Status Code: {{ connectivityResult.status_code }}<br>
                        Content Length: {{ connectivityResult.content_length }}
                    </div>
                </div>
            </div>
            
            <div class="card">
                <h3>Step 2: Test HTML Fetching</h3>
                <button @click="testHtmlFetch" :disabled="loading">Fetch Sample SBC Page</button>
                <div v-if="htmlResult" class="log">
                    <strong>HTML Length:</strong> {{ htmlResult.length }}<br>
                    <strong>Title Found:</strong> {{ htmlResult.title }}<br>
                    <strong>HTML Tags:</strong> H1={{ htmlResult.h1_tags }}, H2={{ htmlResult.h2_tags }}, H3={{ htmlResult.h3_tags }}<br>
                    <strong>Sample:</strong> {{ htmlResult.sample }}
                </div>
            </div>
            
            <div class="card">
                <h3>Step 3: Test Requirement Parsing</h3>
                <button @click="testParsing" :disabled="loading">Test Requirement Extraction</button>
                <div v-if="parseResult" class="log">
                    <strong>Requirements Found:</strong> {{ parseResult.count }}<br>
                    <strong>List Items Found:</strong> {{ parseResult.li_count }}<br>
                    <strong>Sample Requirements:</strong><br>
                    <div v-for="req in parseResult.requirements" :key="req">• {{ req }}</div>
                    <strong>Sample List Items:</strong><br>
                    <div v-for="item in parseResult.li_samples" :key="item">• {{ item }}</div>
                </div>
            </div>
            
            <div class="card">
                <h3>Step 4: Database Status</h3>
                <button @click="checkDatabase" :disabled="loading">Check Database</button>
                <div v-if="dbResult" class="log" :class="dbResult.success ? 'success' : 'error'">
                    {{ dbResult.message }}
                    <div v-if="dbResult.success">
                        <strong>SBC Tables:</strong> {{ dbResult.sbc_tables.join(', ') || 'None found' }}<br>
                        <strong>Player Tables:</strong> {{ dbResult.player_tables.join(', ') || 'None found' }}<br>
                        <strong>Total Tables:</strong> {{ dbResult.total_tables }}
                    </div>
                </div>
            </div>
            
            <div class="card">
                <h3>Step 5: Test New Parser (Based on Real HTML)</h3>
                <button @click="testNewParser" :disabled="loading">Test Updated Parser</button>
                <div v-if="newParserResult" class="log">
                    <strong>Status:</strong> {{ newParserResult.status }}<br>
                    <strong>SBCs Found:</strong> {{ newParserResult.sbcs_found }}<br>
                    <div v-if="newParserResult.sample_sbcs && newParserResult.sample_sbcs.length > 0">
                        <strong>Sample SBCs:</strong><br>
                        <div v-for="sbc in newParserResult.sample_sbcs" :key="sbc.name" class="highlight">
                            • {{ sbc.name }} ({{ sbc.category }}, {{ sbc.challenge_count }} challenges)
                        </div>
                    </div>
                    <div v-if="newParserResult.sample_details">
                        <strong>Sample Details:</strong><br>
                        • URL: {{ newParserResult.sample_details.url }}<br>
                        • Requirements Found: {{ newParserResult.sample_details.requirements_found }}<br>
                        • Sample Requirements:<br>
                        <div v-for="req in newParserResult.sample_details.sample_requirements" :key="req" style="margin-left: 20px;">
                            - {{ req }}
                        </div>
                    </div>
                    <div v-if="newParserResult.error" class="error">
                        <strong>Error:</strong> {{ newParserResult.error }}
                    </div>
                </div>
            </div>
            
            <div class="card">
                <h3>Step 6: Test JSON API Discovery</h3>
                <button @click="testApi" :disabled="loading">Test fut.gg APIs</button>
                <div v-if="apiResult" class="log">
                    <strong>Status:</strong> {{ apiResult.status }}<br>
                    <strong>Endpoints Tested:</strong> {{ apiResult.total_endpoints_tested }}<br>
                    
                    <div v-if="apiResult.analysis">
                        <strong>Successful Endpoints:</strong> {{ apiResult.analysis.successful_endpoints.length }}<br>
                        <div v-for="endpoint in apiResult.analysis.successful_endpoints" :key="endpoint" style="margin: 2px 0;">
                            • {{ endpoint }}
                        </div>
                        
                        <div v-if="apiResult.analysis.json_endpoints && apiResult.analysis.json_endpoints.length > 0">
                            <strong>JSON Endpoints Found:</strong><br>
                            <div v-for="endpoint in apiResult.analysis.json_endpoints" :key="endpoint.endpoint" class="highlight">
                                • <strong>{{ endpoint.endpoint }}</strong><br>
                                Keys: {{ endpoint.keys }}<br>
                                Preview: {{ endpoint.preview }}
                            </div>
                        </div>
                        
                        <div v-if="apiResult.analysis.promising_endpoints && apiResult.analysis.promising_endpoints.length > 0">
                            <strong>Promising Endpoints:</strong><br>
                            <div v-for="endpoint in apiResult.analysis.promising_endpoints" :key="endpoint" class="success">
                                • {{ endpoint }}
                            </div>
                        </div>
                    </div>
                    
                    <div v-if="apiResult.error" class="error">
                        <strong>Error:</strong> {{ apiResult.error }}
                    </div>
                </div>
            </div>
            
            <div class="card">
                <h3>Step 7: Targeted API Test</h3>
                <button @click="testTargetedApi" :disabled="loading">Test High-Priority Endpoints</button>
                <div v-if="targetedResult" class="log">
                    <strong>Status:</strong> {{ targetedResult.status }}<br>
                    <strong>Promising Count:</strong> {{ targetedResult.promising_count }}<br>
                    <div v-if="targetedResult.successful_data_endpoints && targetedResult.successful_data_endpoints.length > 0">
                        <strong>Successful Data Endpoints:</strong><br>
                        <div v-for="endpoint in targetedResult.successful_data_endpoints" :key="endpoint" class="success">
                            • {{ endpoint }}
                        </div>
                    </div>
                    <strong>Recommendation:</strong> {{ targetedResult.recommendation }}
                    <div v-if="targetedResult.error" class="error">
                        <strong>Error:</strong> {{ targetedResult.error }}
                    </div>
                </div>
            </div>
            
            <div class="card">
                <h3>Step 8: Full Crawl Test</h3>
                <button @click="testFullCrawl" :disabled="loading">Run Test Crawl</button>
                <div v-if="crawlResult" class="log">
                    <strong>Status:</strong> {{ crawlResult.status }}<br>
                    <strong>SBCs Found:</strong> {{ crawlResult.count }}<br>
                    <strong>Details:</strong> {{ crawlResult.details }}
                </div>
            </div>
            
            <div v-if="loading" style="text-align: center; margin: 20px;">
                <div style="display: inline-block; width: 20px; height: 20px; border: 2px solid #f3f3f3; border-top: 2px solid #007bff; border-radius: 50%; animation: spin 1s linear infinite;"></div>
                <p>Loading...</p>
            </div>
        </div>
    </div>

    <script>
        const { createApp } = Vue;
        createApp({
            data() {
                return {
                    loading: false,
                    connectivityResult: null,
                    htmlResult: null,
                    parseResult: null,
                    dbResult: null,
                    newParserResult: null,
                    apiResult: null,
                    targetedResult: null,
                    crawlResult: null
                }
            },
            methods: {
                async testConnectivity() {
                    this.loading = true;
                    try {
                        const res = await axios.get('/debug/connectivity');
                        this.connectivityResult = res.data;
                    } catch (e) {
                        this.connectivityResult = { success: false, message: e.message };
                    }
                    this.loading = false;
                },
                async testHtmlFetch() {
                    this.loading = true;
                    try {
                        const res = await axios.get('/debug/html');
                        this.htmlResult = res.data;
                    } catch (e) {
                        this.htmlResult = { error: e.message };
                    }
                    this.loading = false;
                },
                async testParsing() {
                    this.loading = true;
                    try {
                        const res = await axios.get('/debug/parsing');
                        this.parseResult = res.data;
                    } catch (e) {
                        this.parseResult = { error: e.message };
                    }
                    this.loading = false;
                },
                async checkDatabase() {
                    this.loading = true;
                    try {
                        const res = await axios.get('/debug/database');
                        this.dbResult = res.data;
                    } catch (e) {
                        this.dbResult = { success: false, message: e.message };
                    }
                    this.loading = false;
                },
                async testNewParser() {
                    this.loading = true;
                    try {
                        const res = await axios.get('/debug/new-parser');
                        this.newParserResult = res.data;
                    } catch (e) {
                        this.newParserResult = { status: 'error', error: e.message };
                    }
                    this.loading = false;
                },
                async testApi() {
                    this.loading = true;
                    try {
                        const res = await axios.get('/debug/api-test');
                        this.apiResult = res.data;
                    } catch (e) {
                        this.apiResult = { status: 'error', error: e.message };
                    }
                    this.loading = false;
                },
                async testTargetedApi() {
                    this.loading = true;
                    try {
                        const res = await axios.get('/debug/targeted-api-test');
                        this.targetedResult = res.data;
                    } catch (e) {
                        this.targetedResult = { status: 'error', error: e.message };
                    }
                    this.loading = false;
                },
                async testFullCrawl() {
                    this.loading = true;
                    try {
                        const res = await axios.get('/debug/full-crawl');
                        this.crawlResult = res.data;
                    } catch (e) {
                        this.crawlResult = { status: 'error', details: e.message };
                    }
                    this.loading = false;
                }
            }
        }).mount('#app');
    </script>
    <style>
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    </style>
</body>
</html>
    """)

def analyze_api_results(results):
    """Analyze API test results to identify promising endpoints"""
    json_endpoints = []
    successful_endpoints = []
    suspicious_endpoints = []
    
    for endpoint, result in results.items():
        if isinstance(result, dict):
            # Check if endpoint was successful
            if result.get("status") == 200:
                successful_endpoints.append(endpoint)
                
                # Check if it's JSON
                if result.get("is_json"):
                    json_endpoints.append({
                        "endpoint": endpoint,
                        "keys": result.get("json_keys", []),
                        "preview": result.get("json_preview", "")[:100]
                    })
                
                # Check for suspicious but potentially useful endpoints
                if result.get("content_length", 0) > 1000 and "sbc" in result.get("preview", "").lower():
                    suspicious_endpoints.append({
                        "endpoint": endpoint,
                        "reason": "Large content with SBC references",
                        "preview": result.get("preview", "")[:100]
                    })
    
    return {
        "json_endpoints": json_endpoints,
        "successful_endpoints": successful_endpoints,
        "suspicious_endpoints": suspicious_endpoints,
        "total_successful": len(successful_endpoints),
        "total_json": len(json_endpoints)
    }

# Debug endpoints
@app.get("/debug/connectivity")
async def debug_connectivity():
    """Test basic connectivity to fut.gg"""
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.get("https://www.fut.gg/sbc/", timeout=10)
            return {
                "success": True,
                "status_code": response.status_code,
                "message": f"Successfully connected to fut.gg (Status: {response.status_code})",
                "content_length": len(response.text)
            }
    except Exception as e:
        return {
            "success": False,
            "message": f"Connection failed: {str(e)}"
        }

@app.get("/debug/html")
async def debug_html():
    """Test HTML fetching and basic parsing"""
    try:
        import httpx
        from bs4 import BeautifulSoup
        
        async with httpx.AsyncClient() as client:
            response = await client.get("https://www.fut.gg/sbc/upgrades/25-3-gold-upgrade/", timeout=10)
            html = response.text
            
            soup = BeautifulSoup(html, "html.parser")
            title = soup.select_one("title")
            title_text = title.get_text() if title else "No title found"
            
            return {
                "length": len(html),
                "title": title_text,
                "sample": html[:500] + "..." if len(html) > 500 else html,
                "h1_tags": len(soup.select("h1")),
                "h2_tags": len(soup.select("h2")),
                "h3_tags": len(soup.select("h3")),
                "div_tags": len(soup.select("div")),
                "ul_tags": len(soup.select("ul")),
                "li_tags": len(soup.select("li"))
            }
    except Exception as e:
        return {"error": str(e)}

@app.get("/debug/parsing")
async def debug_parsing():
    """Test requirement parsing on a real SBC page"""
    try:
        import httpx
        from bs4 import BeautifulSoup
        
        async with httpx.AsyncClient() as client:
            response = await client.get("https://www.fut.gg/sbc/upgrades/25-3-gold-upgrade/", timeout=10)
            html = response.text
            
            soup = BeautifulSoup(html, "html.parser")
            
            # Look for any text that contains SBC keywords
            all_text = soup.get_text()
            lines = [line.strip() for line in all_text.split('\n') if line.strip()]
            
            # Find lines that look like requirements
            requirement_lines = []
            requirement_keywords = ['min.', 'max.', 'exactly', 'chemistry', 'rating', 'players', 'from', 'squad']
            
            for line in lines:
                line_lower = line.lower()
                if any(keyword in line_lower for keyword in requirement_keywords):
                    if len(line) < 200 and len(line) > 5:  # Reasonable length
                        requirement_lines.append(line)
            
            # Also check for list items specifically
            li_elements = soup.select("li")
            li_texts = [li.get_text(strip=True) for li in li_elements if li.get_text(strip=True)]
            
            return {
                "count": len(requirement_lines),
                "requirements": requirement_lines[:10],  # First 10
                "li_count": len(li_texts),
                "li_samples": li_texts[:10],
                "total_lines": len(lines)
            }
    except Exception as e:
        return {"error": str(e)}

@app.get("/debug/database")
async def debug_database():
    """Test database connection and structure"""
    if not os.getenv("DATABASE_URL"):
        return {"success": False, "message": "DATABASE_URL not set"}
    
    try:
        import asyncpg
        
        # Test basic connection
        conn = await asyncpg.connect(os.getenv("DATABASE_URL"))
        
        # Check if SBC tables exist
        tables = await conn.fetch("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_name LIKE '%sbc%'
        """)
        
        sbc_table_names = [t['table_name'] for t in tables]
        
        # Check for player tables
        player_tables = await conn.fetch("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' AND (
                table_name ILIKE '%player%' OR 
                table_name ILIKE '%card%' OR 
                table_name ILIKE '%fut%'
            )
        """)
        
        player_table_names = [t['table_name'] for t in player_tables]
        
        await conn.close()
        
        return {
            "success": True,
            "message": "Database connection successful",
            "sbc_tables": sbc_table_names,
            "player_tables": player_table_names,
            "total_tables": len(sbc_table_names) + len(player_table_names)
        }
    except Exception as e:
        return {"success": False, "message": f"Database error: {str(e)}"}

@app.get("/debug/new-parser")
async def test_new_parser():
    """Test the new fut.gg parser based on actual HTML structure"""
    try:
        import httpx
        from bs4 import BeautifulSoup
        import re
        
        async def fetch_and_parse_futgg():
            async with httpx.AsyncClient() as client:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
                
                # Get main SBC page
                response = await client.get("https://www.fut.gg/sbc/", headers=headers, timeout=30)
                soup = BeautifulSoup(response.text, "html.parser")
                
                sbcs = []
                
                # Look for SBC containers based on your HTML sample
                # Main containers have: "bg-gray-600 rounded-lg p-1"
                containers = soup.select('div[class*="bg-gray-600"][class*="rounded-lg"]')
                
                for container in containers:
                    # Find SBC link
                    sbc_link = container.select_one('a[href*="/sbc/"]')
                    if not sbc_link:
                        continue
                    
                    href = sbc_link.get('href')
                    if not href or not href.startswith('/sbc/'):
                        continue
                    
                    # Extract title from h3
                    title_elem = container.select_one('h3')
                    title = title_elem.get_text(strip=True) if title_elem else "Unknown"
                    
                    # Extract description
                    desc_elem = container.select_one('p.text-sm')
                    description = desc_elem.get_text(strip=True) if desc_elem else ""
                    
                    # Extract challenge count
                    challenge_count = 0
                    stat_elements = container.select('.text-sm.font-bold')
                    for stat_elem in stat_elements:
                        text = stat_elem.get_text(strip=True)
                        if text.isdigit():
                            # Check if the previous element says "Challenges"
                            prev_elem = stat_elem.find_previous('.text-xs')
                            if prev_elem and 'challenge' in prev_elem.get_text().lower():
                                challenge_count = int(text)
                                break
                    
                    # Determine category
                    category = "unknown"
                    if "/players/" in href:
                        category = "players"
                    elif "/icons/" in href:
                        category = "icons" 
                    elif "/upgrades/" in href:
                        category = "upgrades"
                    
                    sbcs.append({
                        "slug": href,
                        "name": title,
                        "description": description,
                        "category": category,
                        "challenge_count": challenge_count,
                        "url": f"https://www.fut.gg{href}"
                    })
                
                return sbcs
        
        sbcs = await fetch_and_parse_futgg()
        
        # Test parsing one SBC in detail if we found any
        sample_details = None
        if sbcs:
            sample_url = sbcs[0]['url']
            
            async with httpx.AsyncClient() as client:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                detail_response = await client.get(sample_url, headers=headers, timeout=30)
                detail_soup = BeautifulSoup(detail_response.text, "html.parser")
                
                # Look for any requirement-like text
                all_text = detail_soup.get_text()
                lines = [line.strip() for line in all_text.split('\n') if line.strip()]
                
                requirements = []
                requirement_keywords = ['min.', 'max.', 'exactly', 'chemistry', 'rating', 'players']
                
                for line in lines:
                    line_lower = line.lower()
                    if any(keyword in line_lower for keyword in requirement_keywords):
                        if 5 < len(line) < 150:  # Reasonable length
                            requirements.append(line)
                
                sample_details = {
                    "url": sample_url,
                    "title_from_page": detail_soup.select_one('title').get_text() if detail_soup.select_one('title') else "No title",
                    "requirements_found": len(requirements),
                    "sample_requirements": requirements[:5]
                }
        
        return {
            "status": "success",
            "sbcs_found": len(sbcs),
            "sample_sbcs": sbcs[:3],
            "sample_details": sample_details
        }
        
    except Exception as e:
        import traceback
        return {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }

@app.get("/debug/api-test")
async def test_futgg_api():
    """Test if fut.gg has accessible JSON APIs based on the JavaScript"""
    try:
        import httpx
        
        # API endpoints suggested by the JavaScript
        api_endpoints = [
            "/sbc/_sbcListLayout",
            "/api/sbc/list",
            "/api/sbcs", 
            "/sbc/api/list",
            "/_sbcListLayout",
            "/sbc/_layout"
        ]
        
        results = {}
        
        async with httpx.AsyncClient() as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://www.fut.gg/sbc/"
            }
            
            for endpoint in api_endpoints:
                try:
                    full_url = f"https://www.fut.gg{endpoint}"
                    response = await client.get(full_url, headers=headers, timeout=10)
                    
                    results[endpoint] = {
                        "status": response.status_code,
                        "content_type": response.headers.get("content-type", ""),
                        "content_length": len(response.text),
                        "is_json": response.headers.get("content-type", "").startswith("application/json"),
                        "preview": response.text[:200] + "..." if len(response.text) > 200 else response.text
                    }
                    
                    # If it's JSON, try to parse it
                    if results[endpoint]["is_json"]:
                        try:
                            json_data = response.json()
                            results[endpoint]["json_keys"] = list(json_data.keys()) if isinstance(json_data, dict) else "array"
                            results[endpoint]["json_preview"] = str(json_data)[:300] + "..." if len(str(json_data)) > 300 else str(json_data)
                        except:
                            results[endpoint]["json_error"] = "Failed to parse JSON"
                    
                except Exception as e:
                    results[endpoint] = {"error": str(e)}
        
        return {
            "status": "completed",
            "total_endpoints_tested": len(api_endpoints),
            "results": results,
            "analysis": analyze_api_results(results)
        }
        
    except Exception as e:
        import traceback
        return {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }

@app.get("/debug/targeted-api-test")
async def test_targeted_apis():
    """Test specific API endpoints discovered from JavaScript analysis"""
    try:
        import httpx
        import json
        
        # Based on the main-BKSLzfgU.js file, these are high-priority endpoints
        high_priority_endpoints = [
            # Direct module references from the JS
            "/sbc/_sbcListLayout",  # From original JS + confirmed in main file
            "/_sbcListLayout",
            "/assets/_sbcListLayout-OCacVWPE.js",  # The actual module file
            
            # Category-based endpoints from the JS structure
            "/sbc/_sbcListLayout.category",
            "/sbc/category/players/_sbcListLayout", 
            "/sbc/category/icons/_sbcListLayout",
            "/sbc/category/upgrades/_sbcListLayout",
            
            # Common API patterns for the discovered modules
            "/api/sbc/_sbcListLayout",
            "/sbc/api/_sbcListLayout",
            
            # Try to get raw data that feeds these modules
            "/sbc/_sbcListLayout.json",
            "/sbc/data/_sbcListLayout",
            
            # Next.js data patterns
            "/_next/static/chunks/_sbcListLayout.json",
            "/_next/data/build-id/sbc/_sbcListLayout.json",
        ]
        
        results = {}
        successful_data_endpoints = []
        
        async with httpx.AsyncClient() as client:
            # Try different header combinations
            header_sets = [
                # Standard browser headers
                {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "Referer": "https://www.fut.gg/sbc/",
                    "X-Requested-With": "XMLHttpRequest"
                },
                # API client headers
                {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "application/json",
                    "Content-Type": "application/json"
                },
                # Minimal headers (sometimes works when others fail)
                {
                    "Accept": "*/*"
                }
            ]
            
            for endpoint in high_priority_endpoints:
                endpoint_results = []
                
                for i, headers in enumerate(header_sets):
                    try:
                        url = f"https://www.fut.gg{endpoint}"
                        response = await client.get(url, headers=headers, timeout=10)
                        
                        result = {
                            "header_set": i + 1,
                            "status": response.status_code,
                            "content_type": response.headers.get("content-type", ""),
                            "size": len(response.text),
                            "preview": response.text[:500] + "..." if len(response.text) > 500 else response.text
                        }
                        
                        # Deep analysis for successful responses
                        if response.status_code == 200:
                            content = response.text
                            content_lower = content.lower()
                            
                            # Count SBC indicators
                            sbc_keywords = ["sbc", "challenge", "squad", "rating", "chemistry", "player", "eaid", "reward"]
                            sbc_score = sum(content_lower.count(keyword) for keyword in sbc_keywords)
                            result["sbc_score"] = sbc_score
                            
                            # Try to parse as JSON
                            try:
                                data = json.loads(content)
                                result["is_valid_json"] = True
                                result["json_type"] = type(data).__name__
                                
                                if isinstance(data, dict):
                                    result["json_keys"] = list(data.keys())
                                    
                                    # Look for SBC data structure
                                    if "sbcSets" in data or "allSbcs" in data:
                                        result["contains_sbc_data"] = True
                                        successful_data_endpoints.append(endpoint)
                                    
                                    # Check for nested SBC data
                                    for key, value in data.items():
                                        if isinstance(value, list) and value:
                                            sample = value[0] if isinstance(value[0], dict) else {}
                                            sample_keys = list(sample.keys()) if isinstance(sample, dict) else []
                                            if any(sbc_key in sample_keys for sbc_key in ["name", "challengesCount", "eaId"]):
                                                result["likely_sbc_array"] = True
                                                result["sample_sbc_keys"] = sample_keys
                                                successful_data_endpoints.append(endpoint)
                                
                                elif isinstance(data, list) and data:
                                    result["array_length"] = len(data)
                                    if isinstance(data[0], dict):
                                        sample_keys = list(data[0].keys())
                                        result["sample_keys"] = sample_keys
                                        
                                        # Check if this looks like SBC data
                                        if any(key in sample_keys for key in ["name", "challengesCount", "eaId", "url"]):
                                            result["looks_like_sbc_array"] = True
                                            successful_data_endpoints.append(endpoint)
                                
                            except json.JSONDecodeError:
                                # Check if it's JavaScript/module content
                                if content.strip().startswith(("import", "export", "const", "function")):
                                    result["is_javascript_module"] = True
                                    
                                    # Extract any JSON-like data from JS
                                    json_matches = []
                                    import re
                                    json_pattern = r'\{[^{}]*(?:"[^"]*"[^{}]*)*\}'
                                    matches = re.findall(json_pattern, content)
                                    for match in matches[:3]:  # First 3 matches
                                        try:
                                            parsed = json.loads(match)
                                            json_matches.append(parsed)
                                        except:
                                            continue
                                    
                                    if json_matches:
                                        result["extracted_json"] = json_matches
                            
                            # If high SBC score, mark as interesting
                            if sbc_score > 5:
                                result["high_sbc_content"] = True
                                successful_data_endpoints.append(endpoint)
                        
                        endpoint_results.append(result)
                        
                        # If we got a good response, no need to try other headers
                        if response.status_code == 200 and (result.get("is_valid_json") or result.get("sbc_score", 0) > 5):
                            break
                            
                    except Exception as e:
                        endpoint_results.append({
                            "header_set": i + 1,
                            "error": str(e),
                            "status": "failed"
                        })
                
                results[endpoint] = endpoint_results
        
        # Remove duplicates from successful endpoints
        successful_data_endpoints = list(set(successful_data_endpoints))
        
        return {
            "status": "completed",
            "successful_data_endpoints": successful_data_endpoints,
            "total_endpoints_tested": len(high_priority_endpoints),
            "promising_count": len(successful_data_endpoints),
            "results": results,
            "recommendation": "These endpoints should be tested for actual SBC data extraction" if successful_data_endpoints else "No direct data endpoints found, may need to reverse engineer the JavaScript modules"
        }
        
    except Exception as e:
        import traceback
        return {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }

@app.get("/debug/full-crawl")
async def test_full_crawl():
    """Test a full crawl simulation"""
    try:
        import httpx
        from bs4 import BeautifulSoup
        
        async with httpx.AsyncClient() as client:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            
            # Get main page
            response = await client.get("https://www.fut.gg/sbc/", headers=headers, timeout=30)
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Count SBC links
            sbc_links = soup.select('a[href*="/sbc/"]')
            unique_sbcs = set()
            
            for link in sbc_links:
                href = link.get('href')
                if href and href.startswith('/sbc/') and len(href.split('/')) > 3:
                    unique_sbcs.add(href)
            
            return {
                "status": "success",
                "count": len(unique_sbcs),
                "details": f"Found {len(unique_sbcs)} unique SBC pages on the main listing"
            }
    
    except Exception as e:
        return {
            "status": "error", 
            "count": 0,
            "details": f"Crawl failed: {str(e)}"
        }

@app.get("/health")
def health():
    return {"status": "ok", "database": bool(os.getenv("DATABASE_URL"))}

# Simple solution endpoint for testing
@app.get("/api/test-solution")  
def test_solution():
    return {
        "solution": {
            "total_cost": 15000,
            "rating": 84.2,
            "chemistry": 100,
            "players": [
                {"name": "Yann Sommer", "position": "GK", "rating": 84, "price": 3000},
                {"name": "Thiago Silva", "position": "CB", "rating": 86, "price": 18000},
                {"name": "Generic Player", "position": "CM", "rating": 82, "price": 5000}
            ],
            "data_source": "Mock data for testing"
        }
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)

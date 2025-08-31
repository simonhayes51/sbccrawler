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
        .warning-button { background: #e67e22 !important; }
        .warning-button:hover { background: #d35400 !important; }
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
            
            <div class="card">
                <h3>Step 9: Test Enhanced Crawler</h3>
                <button @click="testEnhancedCrawler" :disabled="loading">Test Enhanced Crawler (Browser + Static)</button>
                <div v-if="enhancedCrawlerResult" class="log">
                    <strong>Status:</strong> {{ enhancedCrawlerResult.status }}<br>
                    <div v-if="enhancedCrawlerResult.status === 'success'">
                        <div class="success">
                            <strong>🤖 Dynamic Crawl (with Browser):</strong><br>
                            • SBCs Found: {{ enhancedCrawlerResult.dynamic_crawl.sbcs_found }}<br>
                            • Total Requirements: {{ enhancedCrawlerResult.dynamic_crawl.total_requirements }}<br>
                            • Avg Requirements/SBC: {{ enhancedCrawlerResult.dynamic_crawl.avg_requirements_per_sbc }}
                        </div>
                        
                        <div class="warning" style="margin: 10px 0;">
                            <strong>📄 Static Crawl (HTML only):</strong><br>
                            • SBCs Found: {{ enhancedCrawlerResult.static_crawl.sbcs_found }}<br>
                            • Total Requirements: {{ enhancedCrawlerResult.static_crawl.total_requirements }}<br>
                            • Avg Requirements/SBC: {{ enhancedCrawlerResult.static_crawl.avg_requirements_per_sbc }}
                        </div>
                        
                        <div class="highlight">
                            <strong>📈 Improvement:</strong><br>
                            • Additional Requirements Found: {{ enhancedCrawlerResult.improvement.requirements_improvement }}<br>
                            • Percentage Increase: {{ enhancedCrawlerResult.improvement.percentage_increase }}%
                        </div>
                        
                        <div v-if="enhancedCrawlerResult.dynamic_crawl.sample_sbc" style="margin-top: 15px;">
                            <strong>Sample SBC:</strong><br>
                            <div class="highlight">
                                <strong>Name:</strong> {{ enhancedCrawlerResult.dynamic_crawl.sample_sbc.name }}<br>
                                <strong>Challenges:</strong> {{ enhancedCrawlerResult.dynamic_crawl.sample_sbc.sub_challenges?.length || 0 }}<br>
                                <div v-if="enhancedCrawlerResult.dynamic_crawl.sample_sbc.sub_challenges?.[0]?.requirements">
                                    <strong>Sample Requirements:</strong><br>
                                    <div v-for="req in enhancedCrawlerResult.dynamic_crawl.sample_sbc.sub_challenges[0].requirements.slice(0, 3)" :key="req.text" style="margin-left: 20px;">
                                        • {{ req.text || req.kind }}
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <div v-if="enhancedCrawlerResult.error" class="error">
                        <strong>Error:</strong> {{ enhancedCrawlerResult.error }}<br>
                        <small v-if="enhancedCrawlerResult.details">{{ enhancedCrawlerResult.details }}</small>
                    </div>
                </div>
            </div>

            <div class="card">
                <h3>Step 10: Test Single SBC Enhanced</h3>
                <button @click="testSingleSbcEnhanced" :disabled="loading">Test Enhanced Parsing on Sample SBC</button>
                <div v-if="singleSbcResult" class="log">
                    <strong>Status:</strong> {{ singleSbcResult.status }}<br>
                    <div v-if="singleSbcResult.status === 'success'">
                        <strong>Test URL:</strong> {{ singleSbcResult.test_url }}<br>
                        <strong>SBC Name:</strong> {{ singleSbcResult.sbc_name }}<br>
                        <strong>Challenges Found:</strong> {{ singleSbcResult.challenges_found }}<br>
                        <strong>Total Requirements:</strong> {{ singleSbcResult.total_requirements }}<br>
                        
                        <div v-if="singleSbcResult.sample_challenge" class="highlight">
                            <strong>Sample Challenge:</strong><br>
                            <strong>Name:</strong> {{ singleSbcResult.sample_challenge.name }}<br>
                            <strong>Requirements ({{ singleSbcResult.sample_challenge.requirements?.length || 0 }}):</strong><br>
                            <div v-for="req in singleSbcResult.sample_challenge.requirements?.slice(0, 5)" :key="req.text" style="margin-left: 20px;">
                                • <strong>{{ req.kind }}:</strong> {{ req.text || req.value }}
                            </div>
                        </div>
                    </div>
                    
                    <div v-if="singleSbcResult.error" class="error">
                        <strong>Error:</strong> {{ singleSbcResult.error }}
                    </div>
                </div>
            </div>

            <div class="card">
                <h3>Step 11: Run Production Crawl</h3>
                <button @click="runEnhancedCrawl" :disabled="loading" class="warning-button">Run Full Enhanced Crawl & Store in Database</button>
                <div v-if="productionCrawlResult" class="log">
                    <strong>Status:</strong> {{ productionCrawlResult.status }}<br>
                    <div v-if="productionCrawlResult.status === 'success'" class="success">
                        <strong>SBCs Crawled:</strong> {{ productionCrawlResult.sbcs_crawled }}<br>
                        <strong>SBCs Stored:</strong> {{ productionCrawlResult.sbcs_stored }}<br>
                        <strong>Total Requirements Found:</strong> {{ productionCrawlResult.total_requirements_found }}<br>
                        <strong>Avg Requirements per SBC:</strong> {{ productionCrawlResult.avg_requirements_per_sbc }}<br>
                        <strong>Database Updated:</strong> {{ productionCrawlResult.database_updated ? '✅ Yes' : '❌ No' }}
                    </div>
                    
                    <div v-if="productionCrawlResult.error" class="error">
                        <strong>Error:</strong> {{ productionCrawlResult.error }}
                    </div>
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
                    crawlResult: null,
                    enhancedCrawlerResult: null,
                    singleSbcResult: null,
                    productionCrawlResult: null
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
                },
                async testEnhancedCrawler() {
                    this.loading = true;
                    try {
                        const res = await axios.get('/debug/test-enhanced-crawler');
                        this.enhancedCrawlerResult = res.data;
                    } catch (e) {
                        this.enhancedCrawlerResult = { status: 'error', error: e.message };
                    }
                    this.loading = false;
                },
                async testSingleSbcEnhanced() {
                    this.loading = true;
                    try {
                        const res = await axios.get('/debug/test-single-sbc-enhanced');
                        this.singleSbcResult = res.data;
                    } catch (e) {
                        this.singleSbcResult = { status: 'error', error: e.message };
                    }
                    this.loading = false;
                },
                async runEnhancedCrawl() {
                    this.loading = true;
                    try {
                        const res = await axios.get('/debug/run-enhanced-crawl', { timeout: 300000 }); // 5 minutes
                        this.productionCrawlResult = res.data;
                    } catch (e) {
                        this.productionCrawlResult = { status: 'error', error: e.message };
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

@app.get("/debug/test-enhanced-crawler")
async def test_enhanced_crawler():
    """Test the new enhanced crawler with browser automation"""
    try:
        from enhanced_crawler import crawl_all_sets_enhanced
        
        # Test with browser automation
        print("🔄 Testing enhanced crawler with browser automation...")
        results_dynamic = await crawl_all_sets_enhanced(use_browser=True, debug_first=True)
        
        # Count requirements found
        total_requirements = 0
        for sbc in results_dynamic:
            for challenge in sbc.get('sub_challenges', []):
                total_requirements += len(challenge.get('requirements', []))
        
        # Test with static only for comparison
        print("🔄 Testing enhanced crawler static only...")
        results_static = await crawl_all_sets_enhanced(use_browser=False, debug_first=True)
        
        static_requirements = 0
        for sbc in results_static:
            for challenge in sbc.get('sub_challenges', []):
                static_requirements += len(challenge.get('requirements', []))
        
        return {
            "status": "success",
            "dynamic_crawl": {
                "sbcs_found": len(results_dynamic),
                "total_requirements": total_requirements,
                "avg_requirements_per_sbc": round(total_requirements / len(results_dynamic), 1) if results_dynamic else 0,
                "sample_sbc": results_dynamic[0] if results_dynamic else None
            },
            "static_crawl": {
                "sbcs_found": len(results_static),
                "total_requirements": static_requirements,
                "avg_requirements_per_sbc": round(static_requirements / len(results_static), 1) if results_static else 0
            },
            "improvement": {
                "requirements_improvement": total_requirements - static_requirements,
                "percentage_increase": round(((total_requirements - static_requirements) / max(static_requirements, 1)) * 100, 1)
            }
        }
        
    except ImportError as e:
        return {
            "status": "error",
            "error": "Enhanced crawler not available. Make sure enhanced_crawler.py is in the project directory.",
            "details": str(e)
        }
    except Exception as e:
        import traceback
        return {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }

@app.get("/debug/test-single-sbc-enhanced")
async def test_single_sbc_enhanced():
    """Test enhanced parsing on a single SBC page"""
    try:
        from enhanced_crawler import EnhancedSBCCrawler
        import httpx
        
        test_url = "https://www.fut.gg/sbc/upgrades/25-3-gold-upgrade/"
        
        async with EnhancedSBCCrawler(use_browser=True) as crawler:
            async with httpx.AsyncClient() as client:
                result = await crawler.parse_sbc_page_enhanced(test_url, client)
        
        # Count requirements found
        total_requirements = sum(len(ch.get('requirements', [])) 
                               for ch in result.get('sub_challenges', []))
        
        return {
            "status": "success",
            "test_url": test_url,
            "sbc_name": result.get("name"),
            "challenges_found": len(result.get('sub_challenges', [])),
            "total_requirements": total_requirements,
            "sample_challenge": result.get('sub_challenges', [{}])[0] if result.get('sub_challenges') else None,
            "full_result": result
        }
        
    except Exception as e:
        import traceback
        return {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }

@app.get("/debug/run-enhanced-crawl")
async def run_enhanced_crawl():
    """Run a full enhanced crawl and store in database"""
    try:
        from enhanced_crawler import crawl_all_sets_enhanced
        from db import init_db, upsert_set, mark_all_inactive_before
        from datetime import datetime, timezone
        
        # Initialize database
        await init_db()
        
        # Mark existing records as potentially inactive
        cutoff = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        await mark_all_inactive_before(cutoff)
        
        # Run enhanced crawl
        print("🔄 Starting enhanced crawl...")
        results = await crawl_all_sets_enhanced(use_browser=True, debug_first=False)
        
        # Store results in database
        stored_count = 0
        total_requirements = 0
        
        for sbc_data in results:
            try:
                await upsert_set(sbc_data)
                stored_count += 1
                
                # Count requirements
                for challenge in sbc_data.get('sub_challenges', []):
                    total_requirements += len(challenge.get('requirements', []))
                    
            except Exception as e:
                print(f"⚠️ Failed to store SBC {sbc_data.get('name')}: {e}")
        
        return {
            "status": "success", 
            "sbcs_crawled": len(results),
            "sbcs_stored": stored_count,
            "total_requirements_found": total_requirements,
            "avg_requirements_per_sbc": round(total_requirements / len(results), 1) if results else 0,
            "database_updated": True
        }
        
    except Exception as e:
        import traceback
        return {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }

# Original debug endpoints (keep these)
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

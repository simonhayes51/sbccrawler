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
                <h3>Step 2: Inspect DOM Structure</h3>
                <button @click="inspectDOM" :disabled="loading">Analyze Real HTML Structure</button>
                <div v-if="domResult" class="log">
                    <strong>Status:</strong> {{ domResult.status || 'success' }}<br>
                    <div v-if="domResult.potential_requirements">
                        <strong>Potential Requirements Found:</strong> {{ domResult.potential_requirements.length }}<br>
                        <div v-for="req in domResult.potential_requirements.slice(0, 5)" :key="req.text" class="highlight">
                            <strong>Text:</strong> {{ req.text }}<br>
                            <strong>Parent:</strong> {{ req.parent_tag }} (class: {{ req.parent_class }})
                        </div>
                    </div>
                    
                    <div v-if="domResult.selector_tests">
                        <strong>Selector Test Results:</strong><br>
                        <div v-for="(result, selector) in domResult.selector_tests" :key="selector">
                            <div v-if="result.dynamic_matches > 0" class="success">
                                <strong>✅ {{ selector }}:</strong> {{ result.dynamic_matches }} matches<br>
                                <div v-if="result.sample_dynamic && result.sample_dynamic.length > 0">
                                    Sample: {{ result.sample_dynamic[0] }}
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <div v-if="domResult.error" class="error">
                        <strong>Error:</strong> {{ domResult.error }}
                    </div>
                </div>
            </div>

            <div class="card">
                <h3>Step 3: Test Enhanced Crawler</h3>
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
                <h3>Step 4: Test Single SBC Enhanced</h3>
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
                <h3>Step 6: Test Solution Extraction</h3>
                <button @click="testSolutionExtraction" :disabled="loading">Test Player ID Extraction from Solutions</button>
                <div v-if="solutionResult" class="log">
                    <strong>Status:</strong> {{ solutionResult.status }}<br>
                    <div v-if="solutionResult.status === 'success' || solutionResult.status === 'partial_success'">
                        <strong>Test URL:</strong> {{ solutionResult.test_url }}<br>
                        <strong>Player IDs Found:</strong> {{ solutionResult.player_ids_found }}<br>
                        <strong>Players in Database:</strong> {{ solutionResult.players_in_database || 'N/A' }}<br>
                        
                        <div v-if="solutionResult.sample_player_ids" class="highlight">
                            <strong>Sample Player IDs:</strong><br>
                            {{ solutionResult.sample_player_ids.join(', ') }}
                        </div>
                        
                        <div v-if="solutionResult.sample_players" class="success">
                            <strong>Sample Players from Database:</strong><br>
                            <div v-for="player in solutionResult.sample_players" :key="player.card_id" style="margin-left: 20px;">
                                • {{ player.name }} ({{ player.rating }} OVR, {{ player.position }}) - {{ player.price.toLocaleString() }} coins
                            </div>
                        </div>
                        
                        <div v-if="solutionResult.solution_stats" class="highlight">
                            <strong>Solution Stats:</strong><br>
                            • Total Cost: {{ solutionResult.solution_stats.total_cost.toLocaleString() }} coins<br>
                            • Average Rating: {{ solutionResult.solution_stats.average_rating }}<br>
                            • Player Count: {{ solutionResult.solution_stats.player_count }}
                        </div>
                        
                        <div v-if="solutionResult.database_error" class="warning">
                            <strong>Database Issue:</strong> {{ solutionResult.database_error }}
                        </div>
                    </div>
                    
                    <div v-if="solutionResult.error" class="error">
                        <strong>Error:</strong> {{ solutionResult.error }}
                    </div>
                </div>
            </div>

            <div class="card">
                <h3>Step 7: Run Production Crawl</h3>
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
                    domResult: null,
                    enhancedCrawlerResult: null,
                    singleSbcResult: null,
                    solutionResult: null,
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
                async testSolutionExtraction() {
                    this.loading = true;
                    try {
                        const res = await axios.get('/debug/test-solution-extraction');
                        this.solutionResult = res.data;
                    } catch (e) {
                        this.solutionResult = { status: 'error', error: e.message };
                    }
                    this.loading = false;
                },
                async inspectDOM() {
                    this.loading = true;
                    try {
                        const res = await axios.get('/debug/inspect-dom');
                        this.domResult = res.data;
                    } catch (e) {
                        this.domResult = { status: 'error', error: e.message };
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
                        const res = await axios.get('/debug/run-enhanced-crawl', { timeout: 300000 });
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

@app.get("/debug/inspect-dom")
async def inspect_dom_structure():
    """Deep inspect the actual DOM structure of fut.gg SBC pages"""
    
    try:
        from playwright.async_api import async_playwright
        import httpx
        from bs4 import BeautifulSoup
        
        test_url = "https://www.fut.gg/sbc/players/25-1253-georgia-stanway/"
        
        # First, get static HTML to compare
        async with httpx.AsyncClient() as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            }
            response = await client.get(test_url, headers=headers, timeout=30)
            static_html = response.text
        
        static_soup = BeautifulSoup(static_html, "html.parser")
        
        # Now get dynamic content with browser
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            await page.goto(test_url, wait_until='networkidle', timeout=30000)
            await page.wait_for_timeout(3000)  # Wait for any dynamic content
            
            # Get the full HTML after JavaScript execution
            dynamic_html = await page.content()
            dynamic_soup = BeautifulSoup(dynamic_html, "html.parser")
            
            # Find all possible requirement containers
            debug_info = {
                "test_url": test_url,
                "static_analysis": {},
                "dynamic_analysis": {},
                "selector_tests": {}
            }
            
            # Test our current selectors on both versions
            current_selectors = [
                'div.bg-gray-600.rounded-lg.p-1',
                'div.bg-gray-600 ul.flex.flex-col.gap-1 li.text-xs',
                'ul.flex.flex-col.gap-1 li.text-xs',
                'li.text-xs'
            ]
            
            for selector in current_selectors:
                static_matches = len(static_soup.select(selector))
                dynamic_matches = len(dynamic_soup.select(selector))
                
                debug_info["selector_tests"][selector] = {
                    "static_matches": static_matches,
                    "dynamic_matches": dynamic_matches,
                    "sample_static": [],
                    "sample_dynamic": []
                }
                
                # Get sample text from matches
                for elem in static_soup.select(selector)[:3]:
                    text = elem.get_text(strip=True)
                    if text:
                        debug_info["selector_tests"][selector]["sample_static"].append(text[:100])
                
                for elem in dynamic_soup.select(selector)[:3]:
                    text = elem.get_text(strip=True)
                    if text:
                        debug_info["selector_tests"][selector]["sample_dynamic"].append(text[:100])
            
            # Look for ANY elements that might contain requirements
            requirement_keywords = ['min', 'max', 'exactly', 'chemistry', 'rating', 'players', 'team', 'club', 'league', 'nation']
            
            # Search through all text elements for requirement-like content
            all_elements = dynamic_soup.find_all(text=True)
            potential_requirements = []
            
            for text_node in all_elements:
                text = text_node.strip()
                if (len(text) > 10 and len(text) < 200 and 
                    any(keyword in text.lower() for keyword in requirement_keywords) and
                    any(char.isdigit() for char in text)):
                    
                    # Get the parent element info
                    parent = text_node.parent
                    parent_info = {
                        "text": text,
                        "parent_tag": parent.name if parent else None,
                        "parent_class": parent.get('class') if parent and parent.get('class') else None,
                        "parent_html": str(parent)[:200] + "..." if parent else None
                    }
                    potential_requirements.append(parent_info)
            
            debug_info["potential_requirements"] = potential_requirements[:10]  # First 10 matches
            
            # Look for common SBC structure patterns
            structure_selectors = [
                'div[class*="challenge"]',
                'div[class*="squad"]', 
                'div[class*="requirement"]',
                'div[class*="sbc"]',
                'div[class*="gray"]',
                'ul[class*="flex"]',
                'li[class*="text"]',
                'div.rounded',
                'div.p-1',
                'div.p-2',
                'div.p-4'
            ]
            
            for selector in structure_selectors:
                matches = await page.locator(selector).count()
                if matches > 0:
                    debug_info["selector_tests"][f"structure_{selector}"] = {
                        "dynamic_matches": matches,
                        "sample_dynamic": []
                    }
                    
                    # Get sample content
                    elements = await page.locator(selector).all()
                    for i, elem in enumerate(elements[:2]):
                        try:
                            text_content = await elem.text_content()
                            if text_content and len(text_content.strip()) > 20:
                                debug_info["selector_tests"][f"structure_{selector}"]["sample_dynamic"].append(
                                    text_content.strip()[:150] + "..."
                                )
                        except:
                            pass
            
            await browser.close()
            
            return debug_info
            
    except Exception as e:
        import traceback
        return {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }

@app.get("/debug/test-enhanced-crawler")
async def test_enhanced_crawler():
    """Test the new enhanced crawler with browser automation"""
    try:
        from enhanced_crawler import crawl_all_sets_enhanced
        
        # Test with browser automation - limit to first 3 SBCs for quick testing
        print("🔄 Testing enhanced crawler with browser automation...")
        results_dynamic = await crawl_all_sets_enhanced(use_browser=True, debug_first=True)
        
        # Limit to first 3 for testing
        results_dynamic = results_dynamic[:3]
        
        # Count requirements found
        total_requirements = 0
        for sbc in results_dynamic:
            for challenge in sbc.get('sub_challenges', []):
                total_requirements += len(challenge.get('requirements', []))
        
        # Test with static only for comparison
        print("🔄 Testing enhanced crawler static only...")
        results_static = await crawl_all_sets_enhanced(use_browser=False, debug_first=True)
        results_static = results_static[:3]
        
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
        
        test_url = "https://www.fut.gg/sbc/players/25-1253-georgia-stanway/"
        
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

@app.get("/debug/test-solution-extraction")
async def test_solution_extraction():
    """Test extracting player IDs from solution pages"""
    try:
        from solution_extractor import SolutionExtractor, get_player_data_from_database
        from db import get_pool
        
        test_solution_url = "https://www.fut.gg/25/squad-builder/2e669820-9dc8-4ce7-af74-c75133f074c8/"
        
        # Extract player IDs
        async with SolutionExtractor(use_browser=True) as extractor:
            player_ids = await extractor.get_solution_players(test_solution_url)
        
        if not player_ids:
            return {
                "status": "error",
                "error": "No player IDs found in solution page"
            }
        
        # Get player data from database
        try:
            pool = await get_pool()
            players = await get_player_data_from_database(player_ids, pool)
            
            total_cost = sum(p.get("price", 0) for p in players)
            avg_rating = sum(p.get("rating", 0) for p in players) / len(players) if players else 0
            
            return {
                "status": "success",
                "test_url": test_solution_url,
                "player_ids_found": len(player_ids),
                "players_in_database": len(players),
                "sample_player_ids": player_ids[:5],
                "sample_players": players[:5],
                "solution_stats": {
                    "total_cost": total_cost,
                    "average_rating": round(avg_rating, 1),
                    "player_count": len(players)
                }
            }
            
        except Exception as e:
            return {
                "status": "partial_success",
                "player_ids_found": len(player_ids),
                "sample_player_ids": player_ids[:5],
                "database_error": str(e),
                "note": "Player ID extraction worked, but database lookup failed"
            }
            
    except Exception as e:
        import traceback
        return {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }

@app.get("/solutions/{sbc_name}")
async def get_sbc_solutions(sbc_name: str):
    """Get all solutions for a specific SBC with player data"""
    try:
        from solution_extractor import get_sbc_solutions_with_players
        from db import get_pool
        
        # Construct SBC URL from name
        sbc_url = f"https://www.fut.gg/sbc/players/{sbc_name}/"
        
        pool = await get_pool()
        solutions_data = await get_sbc_solutions_with_players(sbc_url, pool)
        
        return {
            "status": "success",
            "sbc_name": sbc_name,
            **solutions_data
        }
        
    except Exception as e:
        import traceback
        return {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }

@app.get("/player/{card_id}")
async def get_player_by_card_id(card_id: int):
    """Get player data by card_id"""
    try:
        from db import get_pool
        
        pool = await get_pool()
        async with pool.acquire() as conn:
            player = await conn.fetchrow("""
                SELECT card_id, name, rating, position, club, league, nation, price
                FROM fut_players 
                WHERE card_id = $1
            """, card_id)
            
            if not player:
                raise HTTPException(status_code=404, detail=f"Player with card_id {card_id} not found")
            
            return {
                "status": "success",
                "player": dict(player)
            }
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "ok", "database": bool(os.getenv("DATABASE_URL"))}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)

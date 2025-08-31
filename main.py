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
                <h3>Step 2: Test JavaScript Analysis</h3>
                <button @click="testJsAnalysis" :disabled="loading">Analyze Squad Builder JavaScript</button>
                <div v-if="jsAnalysisResult" class="log">
                    <strong>Status:</strong> {{ jsAnalysisResult.status }}<br>
                    <div v-if="jsAnalysisResult.status === 'success'">
                        <strong>JS File Size:</strong> {{ jsAnalysisResult.js_file_size }}<br>
                        
                        <div v-if="jsAnalysisResult.api_endpoints && Object.keys(jsAnalysisResult.api_endpoints).length > 0">
                            <strong>API Endpoints Found:</strong><br>
                            <div v-for="(endpoints, pattern) in jsAnalysisResult.api_endpoints" :key="pattern" class="highlight">
                                <strong>{{ pattern }}:</strong><br>
                                <div v-for="endpoint in endpoints" :key="endpoint" style="margin-left: 20px;">
                                    • {{ endpoint }}
                                </div>
                            </div>
                        </div>
                        
                        <div v-if="jsAnalysisResult.sbc_references && Object.keys(jsAnalysisResult.sbc_references).length > 0">
                            <strong>SBC References:</strong><br>
                            <div v-for="(refs, pattern) in jsAnalysisResult.sbc_references" :key="pattern" class="success">
                                <strong>{{ pattern }}:</strong> {{ refs.join(', ') }}
                            </div>
                        </div>
                        
                        <strong>Recommendation:</strong> {{ jsAnalysisResult.recommendation }}
                    </div>
                    
                    <div v-if="jsAnalysisResult.error" class="error">
                        <strong>Error:</strong> {{ jsAnalysisResult.error }}
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
                <h3>Step 5: Run Production Crawl</h3>
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
                    jsAnalysisResult: null,
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
                async testJsAnalysis() {
                    this.loading = true;
                    try {
                        const res = await axios.get('/debug/analyze-squad-builder-js');
                        this.jsAnalysisResult = res.data;
                    } catch (e) {
                        this.jsAnalysisResult = { status: 'error', error: e.message };
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

@app.get("/debug/analyze-squad-builder-js")
async def analyze_squad_builder_js():
    """Analyze the Squad Builder JavaScript for API patterns"""
    try:
        # The minified JavaScript content from the document
        js_content = """import{n as e,o as s,R as a,Z as i,r as t,_ as l,$ as o,a0 as n,Q as r,l as d,M as c,v as u,y as m,a1 as v,j as p,x as h,U as x,a2 as b,a3 as y}from"./vendor.2.-HZvaLpMr.js";import{S as g,w as j,x as C,y as f,F as _,z as N,A as I,B as q,E as k,l as S,G as P,H as T,I as A,J as E,f as F,T as L,K as R,M,N as D,O,Q as w,U,W as z,X as B,Y as V,Z as H,_ as G,$ as Y,a0 as $,a1 as K,a2 as Q,a3 as W,a4 as J,u as Z,a5 as X,a6 as ee,a7 as se,a8 as ae,a9 as ie,aa as te,ab as le,ac as oe,ad as ne,ae as re,af as de,ag as ce,ah as ue,ai as me,aj as ve,ak as pe,al as he,am as xe,an as be,ao as ye,ap as ge,aq as je,ar as Ce,as as fe,at as _e,au as Ne,av as Ie,aw as qe,ax as ke,ay as Se,az as Pe,aA as Te,aB as Ae,aC as Ee,aD as Fe,h as Le,aE as Re,aF as Me,aG as De,aH as Oe,aI as we,aJ as Ue,aK as ze,aL as Be,aM as Ve,aN as He,aO as Ge,aP as Ye,aQ as $e,n as Ke,L as Qe}from"./apps.2.-D9Nv3rHf.js";import{C as We,a as Je,T as Ze,I as Xe,S as es,b as ss,E as as,u as is,s as ts}from"./EllipsisSolidSvg.2.-orzIb8WP.js"""
        
        import re
        
        # Look for API endpoint patterns in the minified JS
        api_patterns = [
            r'"/api/[^"]*"',
            r'"/sbc/[^"]*"', 
            r'"https://[^"]*api[^"]*"',
            r'fetch\s*\([^)]*\)',
            r'axios\.[^(]*\([^)]*\)',
            r'useQuery\([^)]*\)',
            r'useLazyQuery\([^)]*\)',
            r'useGet[^(]*Query\(',
        ]
        
        found_endpoints = {}
        for pattern in api_patterns:
            matches = re.findall(pattern, js_content, re.IGNORECASE)
            if matches:
                # Clean up matches and remove duplicates
                cleaned_matches = list(set([match.strip('"') for match in matches]))
                found_endpoints[pattern] = cleaned_matches[:10]  # First 10 matches
        
        # Look for specific SBC-related patterns
        sbc_patterns = [
            r'"sbc[^"]*"',
            r'"challenge[^"]*"',
            r'"requirement[^"]*"',
            r'"squad[^"]*"',
            r'getSquad[^(]*\(',
            r'getSbc[^(]*\(',
            r'useGetSbc[^(]*Query\(',
            r'useGetSquad[^(]*Query\(',
        ]
        
        sbc_references = {}
        for pattern in sbc_patterns:
            matches = re.findall(pattern, js_content, re.IGNORECASE)
            if matches:
                cleaned_matches = list(set([match.strip('"') for match in matches]))
                sbc_references[pattern] = cleaned_matches[:5]
        
        # Look for GraphQL or API query patterns
        query_patterns = [
            r'query\s+[A-Z][a-zA-Z]*\s*{[^}]*}',
            r'mutation\s+[A-Z][a-zA-Z]*\s*{[^}]*}',
            r'gql`[^`]*`',
        ]
        
        queries = {}
        for pattern in query_patterns:
            matches = re.findall(pattern, js_content, re.IGNORECASE | re.DOTALL)
            if matches:
                queries[pattern] = matches[:3]
        
        return {
            "status": "success",
            "js_file_size": len(js_content),
            "api_endpoints": found_endpoints,
            "sbc_references": sbc_references,
            "graphql_queries": queries,
            "recommendation": "Check the api_endpoints for actual data fetching URLs"
        }
        
    except Exception as e:
        return {"status": "error", "error": str(e)}

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

@app.get("/health")
def health():
    return {"status": "ok", "database": bool(os.getenv("DATABASE_URL"))}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)

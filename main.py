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
    <script src="https://unpkg.com/vue@3/dist/vue.global.js"></script>
    <script src="https://unpkg.com/axios/dist/axios.min.js"></script>
    <style>
        body { font-family: system-ui; margin: 20px; background: #f0f2f5; }
        .container { max-width: 800px; margin: 0 auto; }
        .card { background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        h1 { color: #333; margin-bottom: 20px; }
        button { padding: 10px 20px; background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; margin: 5px; }
        button:disabled { opacity: 0.6; cursor: not-allowed; }
        .warning-button { background: #e67e22 !important; }
        .log { background: #f8f9fa; padding: 10px; border-radius: 4px; font-family: monospace; font-size: 12px; white-space: pre-wrap; max-height: 400px; overflow-y: auto; }
        .error { background: #f8d7da; color: #721c24; }
        .success { background: #d4edda; color: #155724; }
        .warning { background: #fff3cd; color: #856404; }
        .highlight { background: #e8f5e8; padding: 5px; border-radius: 3px; margin: 5px 0; }
        [v-cloak] { display: none; }
    </style>
</head>
<body>
    <div id="app" v-cloak>
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
                <h3>Step 2: Test Raw HTML Extraction</h3>
                <button @click="testRawHtmlExtraction" :disabled="loading">Test Pattern Matching on Raw HTML</button>
                <div v-if="rawHtmlResult" class="log">
                    <strong>Status:</strong> {{ rawHtmlResult.status }}<br>
                    <div v-if="rawHtmlResult.status === 'success'">
                        <strong>Test URL:</strong> {{ rawHtmlResult.test_url }}<br>
                        <strong>HTML Length:</strong> {{ rawHtmlResult.html_length }} chars<br>
                        
                        <div class="highlight">
                            <strong>WebP Pattern Matches (25-{id}.):</strong> {{ rawHtmlResult.webp_pattern_matches.count }}<br>
                            <div v-if="rawHtmlResult.webp_pattern_matches.player_ids.length > 0">
                                Player IDs: {{ rawHtmlResult.webp_pattern_matches.player_ids.join(', ') }}
                            </div>
                        </div>
                        
                        <div class="success">
                            <strong>WebP Specific Matches (25-{id}.{hash}.webp):</strong> {{ rawHtmlResult.webp_specific_matches.count }}<br>
                            <div v-if="rawHtmlResult.webp_specific_matches.player_ids.length > 0">
                                Player IDs: {{ rawHtmlResult.webp_specific_matches.player_ids.join(', ') }}
                            </div>
                        </div>
                        
                        <div class="highlight">
                            <strong>General 25- Matches:</strong> {{ rawHtmlResult.general_25_matches.count }}<br>
                            <div v-if="rawHtmlResult.general_25_matches.player_ids.length > 0">
                                Player IDs: {{ rawHtmlResult.general_25_matches.player_ids.slice(0, 10).join(', ') }}
                            </div>
                        </div>
                        
                        <div v-if="rawHtmlResult.any_25_occurrences" class="warning">
                            <strong>Any 25- Occurrences:</strong> {{ rawHtmlResult.any_25_occurrences.count }}<br>
                            <div v-if="rawHtmlResult.any_25_occurrences.examples.length > 0">
                                Examples: {{ rawHtmlResult.any_25_occurrences.examples.slice(0, 5).join(', ') }}
                            </div>
                        </div>
                        
                        <div v-if="rawHtmlResult.card_id_json_matches" class="success">
                            <strong>Card ID JSON Matches:</strong> {{ rawHtmlResult.card_id_json_matches.count }}<br>
                            <div v-if="rawHtmlResult.card_id_json_matches.card_ids.length > 0">
                                Card IDs: {{ rawHtmlResult.card_id_json_matches.card_ids.slice(0, 5).join(', ') }}
                            </div>
                        </div>
                        
                        <div v-if="rawHtmlResult.image_url_matches" class="highlight">
                            <strong>Image URL Matches:</strong> {{ rawHtmlResult.image_url_matches.count }}<br>
                            <div v-if="rawHtmlResult.image_url_matches.player_ids.length > 0">
                                Player IDs: {{ rawHtmlResult.image_url_matches.player_ids.slice(0, 5).join(', ') }}
                            </div>
                        </div>
                        
                        <div v-if="rawHtmlResult.html_samples" class="warning" style="margin-top: 15px;">
                            <strong>HTML Analysis:</strong><br>
                            • Contains "25-": {{ rawHtmlResult.html_samples.contains_25_dash ? '✅' : '❌' }}<br>
                            • Contains ".webp": {{ rawHtmlResult.html_samples.contains_webp ? '✅' : '❌' }}<br>
                            • Contains "player": {{ rawHtmlResult.html_samples.contains_player ? '✅' : '❌' }}<br>
                            • Contains "card": {{ rawHtmlResult.html_samples.contains_card ? '✅' : '❌' }}<br>
                            
                            <details style="margin-top: 10px;">
                                <summary><strong>Show HTML Sample (first 1000 chars)</strong></summary>
                                <div style="background: #f0f0f0; padding: 10px; margin-top: 5px; font-size: 10px; max-height: 200px; overflow-y: auto; white-space: pre-wrap;">{{ rawHtmlResult.html_samples.first_1000_chars }}</div>
                            </details>
                        </div>
                    </div>
                    
                    <div v-if="rawHtmlResult.error" class="error">
                        <strong>Error:</strong> {{ rawHtmlResult.error }}
                    </div>
                </div>
            </div>

            <div class="card">
                <h3>Step 3: Test Solution Extraction</h3>
                <button @click="testSolutionExtraction" :disabled="loading">Test Player ID Extraction from Solutions</button>
                <div v-if="solutionResult" class="log">
                    <strong>Status:</strong> {{ solutionResult.status }}<br>
                    <div v-if="solutionResult.status === 'success'">
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
                                • {{ player.name }} ({{ player.rating }} OVR, {{ player.position }}) - {{ player.price || 'No price' }} coins
                            </div>
                        </div>
                        
                        <div v-if="solutionResult.solution_stats" class="highlight">
                            <strong>Solution Stats:</strong><br>
                            • Total Cost: {{ solutionResult.solution_stats.total_cost }} coins<br>
                            • Average Rating: {{ solutionResult.solution_stats.average_rating }}<br>
                            • Player Count: {{ solutionResult.solution_stats.player_count }}
                        </div>
                    </div>
                    
                    <div v-if="solutionResult.error" class="error">
                        <strong>Error:</strong> {{ solutionResult.error }}
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
                    rawHtmlResult: null,
                    solutionResult: null
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
                async testRawHtmlExtraction() {
                    this.loading = true;
                    try {
                        const res = await axios.get('/debug/test-raw-html-extraction');
                        this.rawHtmlResult = res.data;
                    } catch (e) {
                        this.rawHtmlResult = { status: 'error', error: e.message };
                    }
                    this.loading = false;
                },
                async testSolutionExtraction() {
                    this.loading = true;
                    try {
                        const res = await axios.get('/debug/test-solution-extraction');
                        this.solutionResult = res.data;
                    } catch (e) {
                        this.solutionResult = { status: 'error', error: e.message };
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

@app.get("/debug/test-raw-html-extraction")
async def test_raw_html_extraction():
    """Test extracting player IDs from raw HTML content"""
    try:
        import httpx
        import re
        
        # Test with a known solution URL
        test_url = "https://www.fut.gg/25/squad-builder/2e669820-9dc8-4ce7-af74-c75133f074c8/"
        
        async with httpx.AsyncClient() as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            response = await client.get(test_url, headers=headers, timeout=30)
            html_content = response.text
        
        # Look for the webp pattern in raw HTML - FIXED PATTERN
        # Pattern: 25-{player_id}.{anything} - capture everything between 25- and the next dot
        webp_pattern = r'25-(\d+)\.'  # Capture digits between 25- and next dot
        matches = re.findall(webp_pattern, html_content)
        unique_matches = list(set(matches))
        
        # More specific webp pattern
        webp_specific_pattern = r'25-(\d+)\.[a-f0-9]+\.webp'  # Only webp files
        webp_matches = re.findall(webp_specific_pattern, html_content)
        unique_webp_matches = list(set(webp_matches))
        
        # Look for any reference to player IDs in the HTML
        general_pattern = r'25-(\d{6,})'  # 6+ digits after 25-
        general_matches = re.findall(general_pattern, html_content)
        unique_general_matches = list(set(general_matches))general_matches = list(set(general_matches))
        
        # NEW: Look for ANY occurrences of "25-" to see what's actually there
        any_25_pattern = r'25-[^"\s<>]{1,20}'  # Any characters after 25- up to 20 chars
        any_25_matches = re.findall(any_25_pattern, html_content)
        unique_any_25 = list(set(any_25_matches))
        
        # NEW: Look for card_id or cardId patterns
        card_id_patterns = [
            r'"card_id":\s*(\d+)',
            r'"cardId":\s*(\d+)', 
            r'cardId:\s*(\d+)',
            r'card-id["\']:\s*["\'](\d+)',
        ]
        
        card_id_matches = []
        for pattern in card_id_patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            card_id_matches.extend(matches)
        
        unique_card_ids = list(set(card_id_matches))
        
        # NEW: Look for image URLs with different patterns
        img_patterns = [
            r'src="[^"]*player[^"]*(\d{8,})[^"]*"',  # URLs containing "player" with 8+ digits
            r'src="[^"]*cdn[^"]*(\d{8,})[^"]*"',     # CDN URLs with 8+ digits
            r'src="[^"]*fut\.gg[^"]*(\d{8,})[^"]*"',  # fut.gg URLs with 8+ digits
        ]
        
        img_matches = []
        for pattern in img_patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            img_matches.extend(matches)
        
        unique_img_matches = list(set(img_matches))
        
        return {
            "status": "success",
            "test_url": test_url,
            "html_length": len(html_content),
            "webp_pattern_matches": {
                "count": len(unique_matches),
                "player_ids": unique_matches[:10]
            },
            "webp_specific_matches": {
                "count": len(unique_webp_matches),
                "player_ids": unique_webp_matches[:10]
            },
            "general_25_matches": {
                "count": len(unique_general_matches),
                "player_ids": unique_general_matches[:10]
            },
            "any_25_occurrences": {
                "count": len(unique_any_25),
                "examples": unique_any_25[:10]
            },
            "card_id_json_matches": {
                "count": len(unique_card_ids),
                "card_ids": unique_card_ids[:10]
            },
            "image_url_matches": {
                "count": len(unique_img_matches),
                "player_ids": unique_img_matches[:10]
            },
            "html_samples": {
                "first_1000_chars": html_content[:1000],
                "contains_25_dash": "25-" in html_content,
                "contains_webp": ".webp" in html_content,
                "contains_player": "player" in html_content.lower(),
                "contains_card": "card" in html_content.lower(),
            },
            "patterns_tested": [
                "25-(\\d+)\\.([\\w]+)\\.webp",
                "25-(\\d{6,})",
                "25-[^\"\\s<>]{1,20}",
                '"card_id":\\s*(\\d+)',
                'src="[^"]*player[^"]*(\d{8,})[^"]*"'
            ]
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
    """Test extracting player IDs from solution pages with better debugging"""
    try:
        # Try multiple test URLs to find one that works
        test_urls = [
            "https://www.fut.gg/25/squad-builder/2e669820-9dc8-4ce7-af74-c75133f074c8/",
            "https://www.fut.gg/25/squad-builder/123e4567-e89b-12d3-a456-426614174000/",
        ]
        
        results = []
        
        # First, try to find actual solution URLs from an SBC page
        try:
            import httpx
            from bs4 import BeautifulSoup
            import re
            
            sbc_url = "https://www.fut.gg/sbc/players/25-1253-georgia-stanway/"
            
            async with httpx.AsyncClient() as client:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
                response = await client.get(sbc_url, headers=headers, timeout=30)
                soup = BeautifulSoup(response.text, "html.parser")
                
                # Look for solution links
                found_solution_urls = []
                for link in soup.find_all("a", href=True):
                    href = link["href"]
                    if "squad-builder" in href and "25/" in href:
                        if href.startswith("/"):
                            href = "https://www.fut.gg" + href
                        found_solution_urls.append(href)
                
                if found_solution_urls:
                    test_urls = found_solution_urls[:3]  # Use first 3 found URLs
        
        except Exception as e:
            pass  # Continue with default URLs
        
        # Test each URL
        for test_url in test_urls:
            try:
                async with httpx.AsyncClient() as client:
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                    }
                    response = await client.get(test_url, headers=headers, timeout=30)
                    html_content = response.text
                
                # Extract player IDs using multiple patterns
                patterns = [
                    r'25-(\d+)\.[\w]+\.webp',
                    r'25-(\d{6,})',
                ]
                
                all_matches = set()
                for pattern in patterns:
                    matches = re.findall(pattern, html_content)
                    all_matches.update(matches)
                
                # Filter valid IDs
                valid_ids = [m for m in all_matches if 6 <= len(m) <= 12 and m.isdigit()]
                
                if valid_ids:
                    # Try to get player data from database if available
                    try:
                        from db import get_pool
                        
                        pool = await get_pool()
                        int_player_ids = [int(pid) for pid in valid_ids]
                        
                        async with pool.acquire() as conn:
                            rows = await conn.fetch("""
                                SELECT card_id, name, rating, position, club, league, nation, price
                                FROM fut_players 
                                WHERE card_id = ANY($1)
                                ORDER BY rating DESC, price ASC
                            """, int_player_ids)
                            
                            players = [dict(row) for row in rows]
                            
                            total_cost = sum(p.get("price", 0) for p in players if p.get("price"))
                            avg_rating = sum(p.get("rating", 0) for p in players) / len(players) if players else 0
                            
                            return {
                                "status": "success",
                                "test_url": test_url,
                                "extraction_method": "static",
                                "player_ids_found": len(valid_ids),
                                "players_in_database": len(players),
                                "sample_player_ids": valid_ids[:5],
                                "sample_players": players[:5],
                                "solution_stats": {
                                    "total_cost": total_cost,
                                    "average_rating": round(avg_rating, 1),
                                    "player_count": len(players)
                                }
                            }
                            
                    except Exception as db_e:
                        # Return partial success - extraction worked, database failed
                        return {
                            "status": "partial_success",
                            "test_url": test_url,
                            "extraction_method": "static", 
                            "player_ids_found": len(valid_ids),
                            "sample_player_ids": valid_ids[:5],
                            "database_error": str(db_e),
                            "note": "Player ID extraction worked, but database lookup failed"
                        }
                
                else:
                    results.append({
                        "url": test_url,
                        "player_ids_found": 0,
                        "error": "No player IDs found"
                    })
                        
            except Exception as e:
                results.append({
                    "url": test_url,
                    "error": str(e)
                })
        
        # If we get here, none of the URLs worked
        return {
            "status": "error",
            "error": "No player IDs found in any test URLs",
            "tested_urls": len(test_urls),
            "url_results": results,
            "debug_info": {
                "extraction_pattern": "25-(\\d+)\\.([\\w]+)\\.webp",
                "note": "Looking for image URLs with pattern: 25-{player_id}.{hash}.webp"
            }
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

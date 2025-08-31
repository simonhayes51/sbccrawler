#!/usr/bin/env python3
"""
Standalone test script to verify SBC requirement extraction
Run this to test the fixes without starting the full FastAPI server
"""

import asyncio
import sys
import os

# Add current directory to path so we can import our modules
sys.path.insert(0, os.path.dirname(__file__))

async def test_basic_connectivity():
    """Test 1: Basic connectivity to fut.gg"""
    print("🔗 Test 1: Basic Connectivity")
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.get("https://www.fut.gg/sbc/", timeout=10)
            print(f"   ✅ Connected successfully (Status: {response.status_code})")
            print(f"   📊 Content length: {len(response.text)} bytes")
            return True
    except Exception as e:
        print(f"   ❌ Connection failed: {e}")
        return False

async def test_static_html_parsing():
    """Test 2: Parse HTML for requirement-like text"""
    print("\n📄 Test 2: Static HTML Analysis")
    try:
        import httpx
        from bs4 import BeautifulSoup
        
        test_url = "https://www.fut.gg/sbc/players/25-1253-georgia-stanway/"
        
        async with httpx.AsyncClient() as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            response = await client.get(test_url, headers=headers, timeout=30)
            html = response.text
        
        soup = BeautifulSoup(html, "html.parser")
        
        # Look for requirement-like text
        requirement_keywords = ['min', 'max', 'exactly', 'chemistry', 'rating', 'players', 'team', 'club', 'league', 'nation']
        all_text = soup.get_text()
        
        potential_requirements = []
        for line in all_text.split('\n'):
            line = line.strip()
            if (len(line) > 8 and len(line) < 200 and 
                any(keyword in line.lower() for keyword in requirement_keywords) and
                any(char.isdigit() for char in line)):
                potential_requirements.append(line)
        
        # Remove duplicates
        unique_requirements = list(set(potential_requirements))
        
        print(f"   📊 Found {len(unique_requirements)} potential requirements")
        for i, req in enumerate(unique_requirements[:5]):
            print(f"   {i+1}. {req}")
        
        return len(unique_requirements) > 0
        
    except Exception as e:
        print(f"   ❌ Static parsing failed: {e}")
        return False

async def test_browser_parsing():
    """Test 3: Browser-based parsing"""
    print("\n🤖 Test 3: Browser-Based Analysis")
    try:
        from playwright.async_api import async_playwright
        
        test_url = "https://www.fut.gg/sbc/players/25-1253-georgia-stanway/"
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            await page.goto(test_url, wait_until='networkidle', timeout=30000)
            await page.wait_for_timeout(3000)
            
            # Use JavaScript to find requirement text
            requirement_candidates = await page.evaluate("""
                () => {
                    const candidates = [];
                    const keywords = ['min', 'max', 'exactly', 'chemistry', 'rating', 'players', 'team', 'club', 'league', 'nation'];
                    
                    // Get all text nodes
                    const walker = document.createTreeWalker(
                        document.body,
                        NodeFilter.SHOW_TEXT,
                        null,
                        false
                    );
                    
                    let node;
                    while (node = walker.nextNode()) {
                        const text = node.textContent.trim();
                        if (text.length > 8 && text.length < 200 && 
                            keywords.some(k => text.toLowerCase().includes(k)) &&
                            /\\d/.test(text)) {
                            candidates.push(text);
                        }
                    }
                    
                    return [...new Set(candidates)]; // Remove duplicates
                }
            """)
            
            await browser.close()
            
            print(f"   📊 Found {len(requirement_candidates)} requirements via browser")
            for i, req in enumerate(requirement_candidates[:5]):
                print(f"   {i+1}. {req}")
            
            return len(requirement_candidates) > 0
            
    except ImportError:
        print("   ⚠️ Playwright not available - skipping browser test")
        return False
    except Exception as e:
        print(f"   ❌ Browser parsing failed: {e}")
        return False

async def test_enhanced_crawler():
    """Test 4: Full enhanced crawler"""
    print("\n🚀 Test 4: Enhanced Crawler")
    try:
        from enhanced_crawler import EnhancedSBCCrawler
        import httpx
        
        test_url = "https://www.fut.gg/sbc/players/25-1253-georgia-stanway/"
        
        # Test with browser
        try:
            async with EnhancedSBCCrawler(use_browser=True) as crawler:
                async with httpx.AsyncClient() as client:
                    result = await crawler.parse_sbc_page_enhanced(test_url, client)
            
            challenges = result.get('sub_challenges', [])
            total_requirements = sum(len(ch.get('requirements', [])) for ch in challenges)
            
            print(f"   🤖 Browser mode: {len(challenges)} challenges, {total_requirements} requirements")
            
            if challenges:
                sample_challenge = challenges[0]
                print(f"   📋 Sample challenge: '{sample_challenge['name']}'")
                for req in sample_challenge.get('requirements', [])[:3]:
                    print(f"      - {req.get('text', req.get('kind', 'Unknown'))}")
                    
            browser_success = total_requirements > 0
            
        except Exception as e:
            print(f"   ⚠️ Browser mode failed: {e}")
            browser_success = False
        
        # Test with static mode
        try:
            async with EnhancedSBCCrawler(use_browser=False) as crawler:
                async with httpx.AsyncClient() as client:
                    result = await crawler.parse_sbc_page_enhanced(test_url, client)
            
            challenges = result.get('sub_challenges', [])
            total_requirements = sum(len(ch.get('requirements', [])) for ch in challenges)
            
            print(f"   📄 Static mode: {len(challenges)} challenges, {total_requirements} requirements")
            
            static_success = total_requirements > 0
            
        except Exception as e:
            print(f"   ❌ Static mode failed: {e}")
            static_success = False
        
        return browser_success or static_success
        
    except ImportError as e:
        print(f"   ❌ Enhanced crawler import failed: {e}")
        return False

async def test_normalizer():
    """Test 5: Requirement normalization"""
    print("\n🔧 Test 5: Requirement Normalizer")
    try:
        from normalizer import normalize_requirements, norm_requirement
        
        test_requirements = [
            "Min. Team Rating: 84",
            "Min. Chemistry: 95",
            "Min. 2 Players from: Premier League",
            "Exactly 11 Gold Players",
            "Min. 1 Team of the Week OR Team of the Season Player"
        ]
        
        print("   📝 Testing requirement normalization:")
        for req in test_requirements:
            normalized = norm_requirement(req)
            print(f"   '{req}' -> {normalized['kind']}")
        
        # Test batch normalization
        normalized_batch = normalize_requirements(test_requirements)
        print(f"   📊 Normalized {len(normalized_batch)} requirements successfully")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Normalizer test failed: {e}")
        return False

async def main():
    """Run all tests"""
    print("🧪 SBC Requirement Extraction Test Suite")
    print("=" * 50)
    
    tests = [
        ("Basic Connectivity", test_basic_connectivity),
        ("Static HTML Parsing", test_static_html_parsing),
        ("Browser Parsing", test_browser_parsing),
        ("Enhanced Crawler", test_enhanced_crawler),
        ("Requirement Normalizer", test_normalizer)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            success = await test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"   💥 Test crashed: {e}")
            results.append((test_name, False))
    
    print("\n" + "=" * 50)
    print("📊 Test Results Summary")
    print("=" * 50)
    
    passed = 0
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {test_name}")
        if success:
            passed += 1
    
    print(f"\n🎯 Overall: {passed}/{len(results)} tests passed")
    
    if passed == 0:
        print("💥 All tests failed - there may be a fundamental issue")
    elif passed < len(results):
        print("⚠️ Some tests failed - partial functionality available")
    else:
        print("🎉 All tests passed - requirement extraction is working!")
    
    return passed == len(results)

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

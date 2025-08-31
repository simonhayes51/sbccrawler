from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any, Optional
import asyncpg
from datetime import datetime

from db import get_pool
from solution_extractor import SolutionExtractor, get_sbc_solutions_with_players
from player_database import (
    get_players_by_card_ids, 
    analyze_solution_cost, 
    validate_solution_requirements,
    search_players_by_name,
    get_players_by_criteria
)

router = APIRouter(prefix="/api", tags=["solutions"])

@router.get("/solutions/extract/{sbc_slug}")
async def extract_sbc_solutions(sbc_slug: str):
    """Extract solutions for an SBC and return with player data"""
    try:
        pool = await get_pool()
        sbc_url = f"https://www.fut.gg/sbc/players/{sbc_slug}/"
        
        solutions_data = await get_sbc_solutions_with_players(sbc_url, pool)
        
        if not solutions_data["solutions"]:
            return {
                "success": False,
                "message": f"No solutions found for SBC: {sbc_slug}",
                "sbc_url": sbc_url
            }
        
        return {
            "success": True,
            "sbc_slug": sbc_slug,
            "sbc_url": sbc_url,
            **solutions_data
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to extract solutions: {str(e)}")

@router.get("/solutions/analyze")
async def analyze_solution(player_ids: str):
    """Analyze a solution given player card IDs (comma-separated)"""
    try:
        # Parse player IDs
        try:
            card_ids = [int(id.strip()) for id in player_ids.split(",") if id.strip()]
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid player IDs format. Use comma-separated integers.")
        
        if not card_ids:
            raise HTTPException(status_code=400, detail="No valid player IDs provided")
        
        pool = await get_pool()
        analysis = await analyze_solution_cost(card_ids, pool)
        
        return {
            "success": True,
            "analysis": analysis,
            "input_player_ids": card_ids
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@router.post("/solutions/validate")
async def validate_solution(solution_data: Dict[str, Any]):
    """Validate if a solution meets SBC requirements"""
    try:
        player_ids = solution_data.get("player_ids", [])
        requirements = solution_data.get("requirements", [])
        
        if not player_ids:
            raise HTTPException(status_code=400, detail="No player IDs provided")
        
        if not requirements:
            raise HTTPException(status_code=400, detail="No requirements provided")
        
        pool = await get_pool()
        validation = await validate_solution_requirements(player_ids, requirements, pool)
        
        return {
            "success": True,
            "validation": validation
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")

@router.get("/players/search")
async def search_players(
    name: Optional[str] = None,
    min_rating: Optional[int] = None,
    max_rating: Optional[int] = None,
    position: Optional[str] = None,
    league: Optional[str] = None,
    club: Optional[str] = None,
    nation: Optional[str] = None,
    max_price: Optional[int] = None,
    is_special: Optional[bool] = None,
    limit: int = 50
):
    """Search for players with various criteria"""
    try:
        pool = await get_pool()
        
        if name:
            players = await search_players_by_name(name, pool, limit)
        else:
            players = await get_players_by_criteria(
                pool=pool,
                min_rating=min_rating,
                max_rating=max_rating,
                position=position,
                league=league,
                club=club,
                nation=nation,
                max_price=max_price,
                is_special=is_special,
                limit=limit
            )
        
        return {
            "success": True,
            "players": players,
            "count": len(players),
            "search_criteria": {
                "name": name,
                "min_rating": min_rating,
                "max_rating": max_rating,
                "position": position,
                "league": league,
                "club": club,
                "nation": nation,
                "max_price": max_price,
                "is_special": is_special,
                "limit": limit
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

@router.get("/players/card/{card_id}")
async def get_player_by_id(card_id: int):
    """Get detailed player information by card ID"""
    try:
        pool = await get_pool()
        
        async with pool.acquire() as conn:
            player = await conn.fetchrow("""
                SELECT card_id, name, rating, position, club, league, nation, 
                       price, rarity, is_special, card_type, weak_foot, skill_moves,
                       pace, shooting, passing, dribbling, defending, physical
                FROM fut_players 
                WHERE card_id = $1
            """, card_id)
            
            if not player:
                raise HTTPException(status_code=404, detail=f"Player with card_id {card_id} not found")
            
            return {
                "success": True,
                "player": dict(player)
            }
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.get("/solutions/compare")
async def compare_solutions(solution_urls: str):
    """Compare multiple solutions by their URLs (comma-separated)"""
    try:
        # Parse solution URLs
        urls = [url.strip() for url in solution_urls.split(",") if url.strip()]
        
        if not urls:
            raise HTTPException(status_code=400, detail="No solution URLs provided")
        
        if len(urls) > 5:
            raise HTTPException(status_code=400, detail="Maximum 5 solutions can be compared at once")
        
        pool = await get_pool()
        comparisons = []
        
        async with SolutionExtractor(use_browser=True) as extractor:
            for i, url in enumerate(urls, 1):
                try:
                    # Extract player IDs from solution URL
                    player_ids = await extractor.get_solution_players(url)
                    
                    if not player_ids:
                        comparisons.append({
                            "solution_number": i,
                            "url": url,
                            "error": "No player IDs found",
                            "players": []
                        })
                        continue
                    
                    # Convert to integers
                    int_player_ids = []
                    for pid in player_ids:
                        try:
                            int_player_ids.append(int(pid))
                        except ValueError:
                            continue
                    
                    # Analyze solution
                    analysis = await analyze_solution_cost(int_player_ids, pool)
                    
                    comparisons.append({
                        "solution_number": i,
                        "url": url,
                        "player_ids": int_player_ids,
                        "analysis": analysis
                    })
                    
                except Exception as e:
                    comparisons.append({
                        "solution_number": i,
                        "url": url,
                        "error": str(e),
                        "players": []
                    })
        
        # Sort by total cost (cheapest first)
        valid_solutions = [s for s in comparisons if "analysis" in s]
        if valid_solutions:
            valid_solutions.sort(key=lambda x: x["analysis"]["total_cost"])
        
        return {
            "success": True,
            "total_solutions": len(urls),
            "valid_solutions": len(valid_solutions),
            "comparisons": comparisons,
            "cheapest_solution": valid_solutions[0] if valid_solutions else None,
            "most_expensive_solution": valid_solutions[-1] if valid_solutions else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Comparison failed: {str(e)}")

@router.get("/solutions/recommend/{sbc_slug}")
async def recommend_solution(
    sbc_slug: str,
    max_budget: Optional[int] = None,
    preferred_leagues: Optional[str] = None,
    min_rating: Optional[int] = None
):
    """Get recommended solution for an SBC based on criteria"""
    try:
        pool = await get_pool()
        
        # First, get all solutions for the SBC
        sbc_url = f"https://www.fut.gg/sbc/players/{sbc_slug}/"
        solutions_data = await get_sbc_solutions_with_players(sbc_url, pool)
        
        if not solutions_data["solutions"]:
            raise HTTPException(status_code=404, detail=f"No solutions found for SBC: {sbc_slug}")
        
        # Filter solutions based on criteria
        filtered_solutions = []
        preferred_league_list = [l.strip().lower() for l in preferred_leagues.split(",")] if preferred_leagues else []
        
        for solution in solutions_data["solutions"]:
            # Budget filter
            if max_budget and solution["total_cost"] > max_budget:
                continue
            
            # Rating filter
            if min_rating and solution["average_rating"] < min_rating:
                continue
            
            # League preference scoring
            league_score = 0
            if preferred_league_list and solution["players"]:
                for player in solution["players"]:
                    player_league = player.get("league", "").lower()
                    if any(pref_league in player_league for pref_league in preferred_league_list):
                        league_score += 1
                
                # Only include solutions with at least some preferred league players
                if league_score == 0:
                    continue
            
            solution["league_preference_score"] = league_score
            filtered_solutions.append(solution)
        
        if not filtered_solutions:
            return {
                "success": False,
                "message": "No solutions match your criteria",
                "criteria": {
                    "max_budget": max_budget,
                    "preferred_leagues": preferred_leagues,
                    "min_rating": min_rating
                }
            }
        
        # Sort by: 1) League preference, 2) Cost, 3) Rating
        filtered_solutions.sort(key=lambda x: (
            -x.get("league_preference_score", 0),  # Higher league preference first
            x["total_cost"],  # Lower cost first
            -x["average_rating"]  # Higher rating first
        ))
        
        recommended = filtered_solutions[0]
        
        return {
            "success": True,
            "sbc_slug": sbc_slug,
            "criteria": {
                "max_budget": max_budget,
                "preferred_leagues": preferred_leagues,
                "min_rating": min_rating
            },
            "recommended_solution": recommended,
            "alternatives": filtered_solutions[1:3],  # Top 2 alternatives
            "total_matching_solutions": len(filtered_solutions)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Recommendation failed: {str(e)}")

# Include the router in your main FastAPI app
# app.include_router(router)

"""
JARVIS AI — Web & Intelligence Tools (Phase 6)

Tools for fetching information from the web:
- DuckDuckGo Search
- Weather info
- News headlines
- Translation
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from loguru import logger

def register_web_tools(registry) -> None:
    """Register all web-related tools."""

    @registry.register(
        name="web_search",
        description="Search the web for information using DuckDuckGo",
        category="web",
        risk_level="safe",
        examples=["Search for Python tips", "Look up latest AI news"],
    )
    async def web_search(query: str) -> dict:
        """Simple DuckDuckGo search (HTML parsing or Instant Answer API)."""
        logger.info(f"Searching web for: {query}")
        
        # Using Lite/simple API for intelligence
        url = f"https://api.duckduckgo.com/?q={query}&format=json"
        
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url)
                data = resp.json()
                
                result = {
                    "abstract": data.get("AbstractText", ""),
                    "source": data.get("AbstractSource", ""),
                    "url": data.get("AbstractURL", ""),
                    "related": [t.get("FirstURL", "") for t in data.get("RelatedTopics", []) if "FirstURL" in t][:3]
                }
                
                if not result["abstract"]:
                    return {"status": "no_results", "query": query, "message": "Try a more specific search."}
                
                return {"status": "ok", "query": query, "results": result}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @registry.register(
        name="get_weather",
        description="Get current weather for a city",
        category="web",
        risk_level="safe",
        examples=["What's the weather in Delhi?", "How is the weather today?"],
    )
    async def get_weather(city: str = "") -> str:
        """Get weather using wttr.in."""
        if not city:
            # Try to auto-detect via IP
            url = "https://wttr.in?format=3"
        else:
            url = f"https://wttr.in/{city}?format=3"
            
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url)
                return resp.text.strip()
        except Exception:
            return "Unable to fetch weather at the moment."

    @registry.register(
        name="get_news",
        description="Get top news headlines for a topic",
        category="web",
        risk_level="safe",
        examples=["Show me technology news", "What's in the news today?"],
    )
    async def get_news(topic: str = "general") -> dict:
        """Get news via RSS or simple news aggregator."""
        # Note: In a production app, we'd use a News API key. 
        # For now, we search DuckDuckGo News or similar fallback.
        query = f"news about {topic}"
        return await web_search(query)

    logger.info(f"Registered web tools (total: {registry.count})")

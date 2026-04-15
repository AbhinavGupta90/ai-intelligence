"""
LLM integration — uses Groq for fast inference on scoring and summarisation.
"""

import os
import json
import asyncio
from typing import Dict, Any, List, Optional

from src.logger import log


GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "llama-3.3-70b-versatile"


async def call_groq(
    prompt: str,
    system: str = "You are a concise AI research analyst.",
    model: str = None,
    temperature: float = 0.3,
    max_tokens: int = 1024,
) -> str:
    """Call Groq API and return the text response."""
    import aiohttp

    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        log.error("GROQ_API_KEY not set — skipping LLM call")
        return ""

    model = model or os.getenv("LLM_MODEL", DEFAULT_MODEL)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(GROQ_API_URL, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    log.error(f"Groq API error {resp.status}: {text[:300]}")
                    return ""
                data = await resp.json()
                return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log.error(f"Groq API call failed: {e}")
        return ""


async def score_item(item: Dict[str, Any], taste_profile: dict = None) -> Dict[str, Any]:
    """Use LLM to score a single news item for relevance (0-100)."""
    taste_context = ""
    if taste_profile:
        interests = ", ".join(taste_profile.get("interests", []))
        taste_context = f"\nUser interests: {interests}"

    prompt = f"""Rate this AI news item for relevance and importance (0-100).
Consider: technical depth, novelty, practical impact, community buzz.{taste_context}

Title: {item.get('title', 'N/A')}
Source: {item.get('source', 'N/A')}
Summary: {item.get('summary', 'N/A')[:500]}

Respond in JSON: {{"score": <int>, "reason": "<one sentence>"}}"""

    response = await call_groq(prompt, max_tokens=150)

    try:
        result = json.loads(response)
        item["llm_score"] = int(result.get("score", 50))
        item["llm_reason"] = result.get("reason", "")
    except (json.JSONDecodeError, ValueError):
        log.warning(f"Failed to parse LLM score for: {item.get('title', '?')}")
        item["llm_score"] = 50
        item["llm_reason"] = "scoring failed"

    return item


async def batch_score(items: List[Dict], taste_profile: dict = None, concurrency: int = 5) -> List[Dict]:
    """Score multiple items with bounded concurrency."""
    semaphore = asyncio.Semaphore(concurrency)

    async def _score(item):
        async with semaphore:
            return await score_item(item, taste_profile)

    results = await asyncio.gather(*[_score(i) for i in items])
    log.info(f"LLM scored {len(results)} items")
    return list(results)


async def generate_summary(items: List[Dict], max_items: int = 15) -> str:
    """Generate a narrative daily digest summary."""
    top_items = sorted(items, key=lambda x: x.get("llm_score", 0), reverse=True)[:max_items]

    bullets = "\n".join(
        f"- [{it.get('source', '?')}] {it.get('title', 'N/A')} (score: {it.get('llm_score', '?')})"
        for it in top_items
    )

    prompt = f"""Write a concise daily AI digest summary (3-5 paragraphs) from these top stories:

{bullets}

Focus on: key themes, breakthroughs, and why they matter. Be specific, not generic."""

    return await call_groq(prompt, max_tokens=800)

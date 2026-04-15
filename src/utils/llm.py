"""
Unified LLM interface — routes to the best available FREE backend.
All modules use this instead of calling APIs directly.

Priority: GROQ_API_KEY (free Llama 3.3 70B) > ANTHROPIC_API_KEY (paid) > None (skip)
Get free Groq key: https://console.groq.com/keys
"""

import os
import json
import asyncio
from src.utils.logger import get_logger

log = get_logger("utils.llm")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")


def get_backend() -> str:
    """Return active LLM backend name."""
    if GROQ_API_KEY:
        return "groq"
    if ANTHROPIC_API_KEY:
        return "anthropic"
    return "none"


async def generate(
    prompt: str,
    system: str = "",
    max_tokens: int = 500,
    temperature: float = 0.3,
) -> str | None:
    """
    Generate text using the best available LLM backend.
    Returns the response text, or None if no backend is available.
    """
    backend = get_backend()

    if backend == "none":
        log.warning("no_llm_backend", msg="No GROQ_API_KEY or ANTHROPIC_API_KEY set")
        return None

    try:
        if backend == "groq":
            return await _generate_groq(prompt, system, max_tokens, temperature)
        else:
            return await _generate_anthropic(prompt, system, max_tokens, temperature)
    except Exception as e:
        log.error("llm_generate_failed", backend=backend, error=str(e))
        return None


async def _generate_groq(
    prompt: str, system: str, max_tokens: int, temperature: float
) -> str:
    """Generate via Groq (FREE — Llama 3.3 70B, blazing fast)."""
    from groq import AsyncGroq

    client = AsyncGroq(api_key=GROQ_API_KEY)

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = await client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return response.choices[0].message.content.strip()


async def _generate_anthropic(
    prompt: str, system: str, max_tokens: int, temperature: float
) -> str:
    """Generate via Anthropic Claude Sonnet (paid fallback)."""
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=max_tokens,
        system=system or "",
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()

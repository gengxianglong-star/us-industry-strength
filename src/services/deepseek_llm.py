"""DeepSeek chat completions (OpenAI-compatible API)."""

from __future__ import annotations

import os
from typing import Any

import requests
from dotenv import load_dotenv

from src.logging_config import get_logger

logger = get_logger(__name__)

load_dotenv()

DEEPSEEK_API_KEY: str | None = os.environ.get("DEEPSEEK_API_KEY") or None
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
PRIMARY_MODEL = "deepseek-v4-flash"
FALLBACK_MODEL = "deepseek-v4-pro"


def is_available() -> bool:
    return bool(DEEPSEEK_API_KEY)


def chat(
    prompt: str,
    *,
    max_tokens: int = 256,
    temperature: float = 0.3,
    thinking: str = "disabled",
) -> tuple[str, str]:
    """Run a chat completion. Returns ``(text, model_used)``."""
    if not DEEPSEEK_API_KEY:
        raise RuntimeError("DEEPSEEK_API_KEY missing")

    last_error: Exception | None = None
    for model in (PRIMARY_MODEL, FALLBACK_MODEL):
        try:
            text = _chat_once(
                prompt,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                thinking=thinking,
            )
            return text, model
        except Exception as exc:
            last_error = exc
            logger.warning("DeepSeek call failed for %s: %s", model, exc)

    raise RuntimeError(f"DeepSeek chat failed: {last_error}") from last_error


def probe(prompt: str = "Reply with exactly: OK") -> dict[str, Any]:
    """Lightweight connectivity check for CI/local scripts."""
    result: dict[str, Any] = {
        "deepseek_api_key_set": is_available(),
        "primary_model": PRIMARY_MODEL,
        "fallback_model": FALLBACK_MODEL,
        "probe_ok": False,
    }
    if not is_available():
        result["error"] = "DEEPSEEK_API_KEY missing"
        return result
    try:
        text, model = chat(prompt, max_tokens=16, temperature=0.0)
        result["probe_ok"] = bool(text)
        result["model_used"] = model
        result["sample"] = text[:80]
    except Exception as exc:
        result["error"] = str(exc)
    return result


def _chat_once(
    prompt: str,
    *,
    model: str,
    max_tokens: int,
    temperature: float,
    thinking: str,
) -> str:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "thinking": {"type": thinking},
    }
    resp = requests.post(
        f"{DEEPSEEK_BASE_URL}/chat/completions",
        headers={
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=90,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:400]}")

    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("DeepSeek returned no choices")

    message = choices[0].get("message") or {}
    content = (message.get("content") or "").strip()
    if not content:
        raise RuntimeError("DeepSeek returned empty content")
    return content

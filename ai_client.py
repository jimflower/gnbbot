"""
AI client — calls Anthropic API directly via the Python SDK.
"""

import logging
import anthropic
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, SYSTEM_PROMPT

log = logging.getLogger(__name__)

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def call_ai(messages: list[dict], system_prompt: str = "") -> str | None:
    """
    Call Claude with a conversation history.

    Args:
        messages: List of {"role": "user"|"assistant", "content": str}
        system_prompt: Override system prompt (falls back to config default)

    Returns:
        Response text, or None on failure.
    """
    try:
        response = _get_client().messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            system=system_prompt or SYSTEM_PROMPT,
            messages=messages,
        )
        return response.content[0].text
    except Exception as e:
        log.error(f"Anthropic API error: {e}")
        return None
